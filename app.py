"""
Chainlit Chat Application with Milvus Vectorstore and Structured Output.

This application uses Chainlit to interact with an LLM (via LangChain) and a Milvus vectorstore.
It supports user authentication (via OAuth), collection selection, and uses a custom output parser
to format answers with their corresponding metadata sources.
"""

#import libraries
import httpx
from typing import cast, List
import tiktoken
from pydantic import BaseModel, Field

import chainlit as cl
from chainlit.input_widget import Select

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts.chat import ChatPromptTemplate
from langchain_core.prompts.image import ImagePromptTemplate
from langchain.schema.runnable import Runnable
from langchain.schema.runnable import RunnableLambda
from langchain.schema.runnable.config import RunnableConfig
from langchain_milvus import Milvus
from langchain.retrievers import EnsembleRetriever
from langchain.schema import StrOutputParser

import base64
from openai import OpenAI

client = OpenAI()

try:
    ENCODER = tiktoken.encoding_for_model("gpt-4")
except KeyError:
    ENCODER = tiktoken.get_encoding("cl100k_base")

def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
    
# Initialize embeddings (used by vectorstore and LLM)
embeddings = OpenAIEmbeddings()
MILVUS_URI = "tcp://standalone:19530"


import os
import smtplib
import anyio
from email.message import EmailMessage

# # ── Email configuration ──────────────────────────────────────────────────────
# EMAIL_HOST     = os.getenv("EMAIL_HOST", "smtp.gmail.com")
# EMAIL_PORT     = int(os.getenv("EMAIL_PORT", 587))
# EMAIL_USER     = os.getenv("EMAIL_USER")            # e.g. your “no-reply@optit.in”
# EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")        # e.g. an SMTP app password
# SUPPORT_EMAIL  = os.getenv("SUPPORT_EMAIL", "support@optit.in")

# def _send_email_blocking(subject: str, body: str, to_address: str = SUPPORT_EMAIL):
#     msg = EmailMessage()
#     msg["From"]    = EMAIL_USER
#     msg["To"]      = to_address
#     msg["Subject"] = subject
#     msg.set_content(body)

#     with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as smtp:
#         smtp.starttls()
#         smtp.login(EMAIL_USER, EMAIL_PASSWORD)
#         smtp.send_message(msg)
#    #remove if not required

# -----------------------------------------------------------------------------
# OAuth Callback
# -----------------------------------------------------------------------------

@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict,
    default_user: cl.User,
) -> cl.User:
    """
    OAuth callback to clean up group names and store them in the user metadata.
    """
    print(raw_user_data)
    groups = raw_user_data.get("groups", [])
    cleaned_groups = [group.lstrip("/") for group in groups]
    default_user.metadata["groups"] = cleaned_groups

    # Add the primary group to the user metadata.
    primary_group = raw_user_data.get("primary_group")
    if primary_group:
        default_user.metadata["primary_group"] = primary_group
    return default_user

# -----------------------------------------------------------------------------
# Vectorstore Initialization
# -----------------------------------------------------------------------------

def initialize_vectorstores(collection_name: str):
    """
    Initialize and return a Milvus vectorstore for the given collection name.
    """
    vectorstore = Milvus(
        collection_name=collection_name,
        embedding_function=embeddings,
        connection_args={"uri": MILVUS_URI},
        auto_id=True
    )
    return vectorstore

# -----------------------------------------------------------------------------
# Structured Output Schema and Parser
# -----------------------------------------------------------------------------

class AnswerWithSources(BaseModel):
    """
    Schema for an answer with associated metadata sources.
    """
    answer: str = Field(default=None, description="answer to the question. if answer is present in the context then give it more importance. Always respond *only* in markdown: use **bold**, _italics_, headings (`#`), lists (`- `), and fenced code blocks (```...```). Dont use header size h1 or h2")
    sources: List[str] = Field(
        default_factory=list,
        description="List of sources metadata used to answer the question. If answer is not from the source then say AI knowledge"
    )

def answer_with_sources_parser(output: AnswerWithSources) -> str:
    """
    Serialize the AnswerWithSources model to a string.
    """
    return f"{output.answer}\nSources: {', '.join(output.sources) if output.sources else 'AI knowledge'}"

# Wrap the parser in a RunnableLambda
output_parser = RunnableLambda(func=answer_with_sources_parser)

# -----------------------------------------------------------------------------
# Runnable (LLM Prompt) Initialization
# -----------------------------------------------------------------------------

def initialize_runnable() -> Runnable:
    """
    Create and return a runnable (LLM pipeline) with a specific prompt.
    
    The prompt instructs the LLM to produce an answer and full metadata sources in a 
    predefined text format.
    """
    llm = ChatOpenAI(model = "gpt-4.1-mini",streaming=True)
    structured_llm = llm.with_structured_output(schema=AnswerWithSources)
    prompt = ChatPromptTemplate.from_messages([
        (   
            "system",
            (
                "You are a helpful chatbot. "
                "Consider the following conversation history and context:\n"
                "Conversation History:\n{chat_history}\n"   
                "Context:\n{context}\n"
                "Always respond *only* in markdown: use **bold**, _italics_, headings (`#`), lists (`- `), and fenced code blocks (```...```).Dont use header size h1 or h2"
                "Answer the problem in detail."
            )
        ),
        ("human", "{question}")
    ])
    return prompt | structured_llm | output_parser

# -----------------------------------------------------------------------------
# Chainlit Event Callbacks
# -----------------------------------------------------------------------------

@cl.on_chat_start
async def on_chat_start():
    """
    Callback executed when the chat starts:
      - Retrieves user info and available collections.
      - Presents a select widget to choose a collection.
      - Initializes default and active vectorstores.
      - Sets up the LLM prompt (runnable) and initializes chat history.
      - Sends an HTTP request with the current session ID.
    """
    user = cl.user_session.get("user")
    print("user is ", user)
    
    # Retrieve available collections from user groups if available.
    if user and "groups" in user.metadata and user.metadata["groups"]:
        available_collections = user.metadata["groups"]
    if user and "groups" in user.metadata:
        # drop “default” and “pod_admin”
        available_collections = [
            g for g in user.metadata["groups"]
            if g not in ("default", "pod_admin")
        ]
    else:
        available_collections = []
    
    # Check for primary_group in the user metadata and determine its position.
    primary_group = user.metadata.get("primary_group") if user else None
    try:
        # If primary_group is in the list, set that as the initial index.
        initial_index = available_collections.index(primary_group)
    except (ValueError, TypeError):
        # Otherwise, default to index 0.
        initial_index = 0

    # Present collection selection widget with the determined initial index.
    settings = await cl.ChatSettings([
        Select(
            id="collection",
            label="Select Organization",
            values=available_collections,
            initial_index=initial_index,
        )
    ]).send()
    
    selected_collection = settings["collection"]
    cl.user_session.set("collection_name", selected_collection)
    
    # Initialize and store vectorstores.
    vectorstore_default = initialize_vectorstores("default")
    cl.user_session.set("vectorstore_default", vectorstore_default)
    vectorstore_active = initialize_vectorstores(selected_collection)
    cl.user_session.set("vectorstore_active", vectorstore_active)
    print(f"Active vectorstore set to: {vectorstore_active.collection_name}")

    # Initialize LLM prompt and chat history.
    runnable = initialize_runnable()
    cl.user_session.set("runnable", runnable)
    cl.user_session.set("chat_history", "")
    print("Session id:", cl.user_session.get("id"))

@cl.on_settings_update
async def setup_agent(settings):
    """
    Callback executed when chat settings are updated:
      - Updates the active vectorstore based on the new collection.
    """
    selected_collection = settings["collection"]
    vectorstore_active = initialize_vectorstores(selected_collection)
    cl.user_session.set("vectorstore_active", vectorstore_active)
    print(f"Active vectorstore changed on setting to: {vectorstore_active.collection_name}")

@cl.on_chat_resume
async def on_chat_resume(thread):
    """
    Callback executed when the chat is resumed:
      - Re-presents the collection selection widget if necessary.
      - Re-initializes vectorstore and runnable if not present in session.
    """
    user = cl.user_session.get("user")
    print("user is ", user)

    # Retrieve available collections from user groups if available.
    if user and "groups" in user.metadata and user.metadata["groups"]:
        available_collections = user.metadata["groups"]
    if user and "groups" in user.metadata:
        # drop “default” and “pod_admin”
        available_collections = [
            g for g in user.metadata["groups"]
            if g not in ("default", "pod_admin")
        ]
    else:
        available_collections = []

    # Check for primary_group in the user metadata and determine its position.
    primary_group = user.metadata.get("primary_group") if user else None
    try:
        # If primary_group is in the list, set that as the initial index.
        initial_index = available_collections.index(primary_group)
    except (ValueError, TypeError):
        # Otherwise, default to index 0.
        initial_index = 0

    # Present collection selection widget.
    settings = await cl.ChatSettings([
        Select(
            id="collection",
            label="Select Organization",
            values=available_collections,
            initial_index=initial_index,
        )
    ]).send()
    selected_collection = settings["collection"]
    # Reinitialize vectorstore if missing.
    if not cl.user_session.get("vectorstore_default") or not cl.user_session.get("vectorstore_active"):
        vectorstore_default = initialize_vectorstores("default")
        cl.user_session.set("vectorstore_default", vectorstore_default)
        vectorstore_active = initialize_vectorstores(selected_collection)
        cl.user_session.set("vectorstore_active", vectorstore_active)

    # Reinitialize runnable if missing.
    if not cl.user_session.get("runnable"):
        runnable = initialize_runnable()
        cl.user_session.set("runnable", runnable)

@cl.on_message
async def on_message(message: cl.Message):
    """
    Callback executed when a new chat message is received:
      - Retrieves the question from the message.
      - Gets vectorstores from the session.
      - Uses an EnsembleRetriever to fetch relevant documents.
      - Updates the conversation history.
      - Streams the answer from the LLM.
      - Parses the aggregated response using the custom parser.
      - Updates the message with the final answer and corresponding document sources.
    """
    print("Received message:", message.__dict__)
    question = message.content

    # 1) pull history early
    chat_history = cl.user_session.get("chat_history") or ""
    
    # # ─── Catch “email support” requests ───────────────────────────────
    # trigger = question.lower()
    # if "email support" in trigger or "send email" in trigger or "contact support" in trigger:
    #     # Build subject/body from user request + history
    #     subject = f"[Support Request] from {cl.user_session.get('user').display_name or 'anonymous'}"
    #     body = (
    #         f"User requested support via the chatbot:\n\n"
    #         f"▶ Question: {question}\n\n"
    #         f"--- Conversation History ---\n{chat_history}"
    #     )

    #     # Run blocking SMTP send in a background thread
    #     await anyio.to_thread.run_sync(_send_email_blocking, subject, body)

    #     # Confirm back to the user
    #     await cl.Message(
    #         content="📧 Your request has been sent to customer support. They will reach out to you shortly!"
    #     ).send()
    #     return
    
    # 1) Fetch vectorstores and do retrieval
    vs_default = cl.user_session.get("vectorstore_default")
    vs_active  = cl.user_session.get("vectorstore_active")
    if not vs_default or not vs_active:
        await cl.Message(content="📛 Vectorstores not initialized.").send()
        return

    ensemble = EnsembleRetriever(
        retrievers=[vs_default.as_retriever(), vs_active.as_retriever()],
        weights=[0.7, 0.3]
    )
    docs = ensemble.invoke(question)

    print(len(ENCODER.encode(docs[0].page_content)), "tokens in first doc\n")

    # 2) Update chat history
    chat_history = cl.user_session.get("chat_history") or ""
    chat_history += f"User: {question}\n"

    # 3) Decide which runnable to call
    #    - If there’s an image element, use the image runnable
    #    - Otherwise, fall back to text-only
    elem = None
    for e in message.elements:
        if getattr(e, "mime", "").startswith("image/"):
            elem = e
            break

    msg = cl.Message(content="")           # single Message instance
    aggregated_response = ""               # one buffer for the answer

    if elem:
        print("Image found in message elements",elem)
        b64  = encode_image(elem.path)
        mime = elem.mime
        # 1) Build the image prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an assistant that can both describe images and read any text in them. This description will be stored in vector store to answer user questions later."),
            ("user", [
                {"type": "text", "text": "1) Describe all visual elements in detail."},
                {"type": "text", "text": "2) Perform OCR and list every piece of text you find."},
                {"type": "text", "text": "3) if a image is present, says image description and then describe the image in detail. So we can differentiate between text and image description."},
                {"type": "image_url", "image_url": {
                "url": f"data:{mime};base64,{b64}",
                "detail": "auto"
                }}
            ])
        ])  

        # 3) Hook it up with your LLM
        llm = ChatOpenAI(model="gpt-4.1-mini", streaming=True)
        chain = prompt | llm

        
        # 4) Invoke it with your variables
        image_description = chain.invoke({})
        print("Image description:", image_description)
        image_description_text = image_description.content

        question = f"Answer the question based on the image and context:\n{image_description_text}\n{question}"

        docs = ensemble.invoke(question)
        
    print("docs:",docs)

    # --- Text-only branch ---
    runnable_txt = cast(Runnable, cl.user_session.get("runnable"))
    async for chunk in runnable_txt.astream(
        {
            "question":     question,
            "context":      docs,
            "chat_history": chat_history,
        },
        config=RunnableConfig(callbacks=[cl.LangchainCallbackHandler()]),
    ):
        token = getattr(chunk, "content", str(chunk))
        aggregated_response += token
        await msg.stream_token(chunk)

    # 4) Send final message and update history
    print(len(ENCODER.encode(aggregated_response)), "tokens in final response\n")
    await msg.send()
    chat_history += f"Bot: {aggregated_response}\n"
    cl.user_session.set("chat_history", chat_history)

    # 5) Handle PDF source attachments
    if "Sources:" in aggregated_response:
        sources_part = aggregated_response.split("Sources:")[1]
        for src in (s.strip() for s in sources_part.split(",")):
            if src.lower().endswith(".pdf"):
                msg.elements.append(cl.Pdf(name=src, display="side", path=src))
        await msg.update()

