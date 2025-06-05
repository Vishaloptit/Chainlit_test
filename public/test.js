// Function to fetch user groups from our custom endpoint.
async function fetchUserGroups() {
  try {
    const response = await fetch("/api/user-groups", { credentials: "include" });
    const data = await response.json();
    return data.groups || [];
  } catch (e) {
    console.error("Failed to fetch user groups:", e);
    return [];
  }
}

// Make sure we catch the watermark even if it appears late:
function patchWatermark() {
  const wm = document.querySelector("a.watermark");
  if (!wm) return;
  wm.href   = "https://optit.in/";
  wm.target = "_blank";
}

// Run immediately in case it's already there:
patchWatermark();
// And observe the DOM in case it appears later:
new MutationObserver(patchWatermark)
  .observe(document.body, { childList: true, subtree: true });

document.addEventListener("DOMContentLoaded", async function () {

  const userGroups = await fetchUserGroups();

  // 2) Drop "default" and "pod_admin"
  const filteredGroups = userGroups.filter(
    g => g !== "default" && g !== "pod_admin"
  );

  // Only show tip ONCE
  let customTextAdded = false;
  function addTextNearSettings() {
    if (customTextAdded) return;
    const settingsButton = document.getElementById("chat-settings-open-modal");
    if (!settingsButton) return;
    if (document.getElementById("my-custom-text")) return;

    const textSpan = document.createElement("span");
    textSpan.id = "my-custom-text";
    textSpan.innerText = "<--change organization to query docs";
    textSpan.style.marginLeft = "8px";
    textSpan.style.color = "#22c55e";
    textSpan.style.transition = "opacity 1s";
    settingsButton.parentNode.insertBefore(textSpan, settingsButton.nextSibling);

    customTextAdded = true; // Don't show again

    setTimeout(() => {
      textSpan.style.opacity = "0";
      setTimeout(() => textSpan.remove(), 1000);
    }, 5000);
  }

  // Try to add tip immediately in case already in DOM
  addTextNearSettings();

  // Use a MutationObserver to watch for settings button just ONCE
  const settingsObserver = new MutationObserver(() => {
    addTextNearSettings();
    if (customTextAdded) settingsObserver.disconnect();
  });
  settingsObserver.observe(document.body, { childList: true, subtree: true });

  // Only add the upload button if the user has the "pod_admin" group.
  if (userGroups.includes("pod_admin")) {
    function uploadFile(file, selectedGroup, statusIcon) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("collection_name", selectedGroup);

      const sessionCookie = document.cookie
        .split("; ")
        .find((row) => row.startsWith("chainlit_session="));
      if (sessionCookie) {
        const sessionId = sessionCookie.split("=")[1];
        formData.append("session_id", sessionId);
      }

      statusIcon.style.display = "block";
      const spinner   = statusIcon.querySelector('.loading-spinner');
      const checkmark = statusIcon.querySelector('.success-check');
      const cross     = statusIcon.querySelector('.error-cross');

      // reset states
      spinner.style.display   = "block";
      checkmark.classList.remove('show');
      cross.classList.remove('show');

      fetch("/api/upload-milvus", {
        method:      "POST",
        credentials: "include",
        body:         formData,
      })
        .then((response) => response.json())
        .then((data) => {
          spinner.style.display = "none";

          if (data.success) {
            checkmark.style.animation = "checkmark-pop 0.3s ease-out forwards";
            checkmark.classList.add('show');
          } else {
            cross.style.animation = "cross-pop 0.3s ease-out forwards";
            cross.classList.add('show');
          }

          setTimeout(() => {
            statusIcon.style.display    = "none";
            spinner.style.display       = "block";
            checkmark.classList.remove('show');
            checkmark.style.animation   = "";
            cross.classList.remove('show');
            cross.style.animation       = "";
          }, 2000);
        })
        .catch((error) => {
          console.error("Upload failed with error:", error);
          spinner.style.display = "none";
          cross.style.animation = "cross-pop 0.3s ease-out forwards";
          cross.classList.add('show');

          setTimeout(() => {
            statusIcon.style.display  = "none";
            spinner.style.display     = "block";
            cross.classList.remove('show');
            cross.style.animation     = "";
          }, 2000);
        });
    }

    function triggerFileInput(selectedGroup, statusIcon) {
      const fileInput = document.createElement("input");
      fileInput.type     = "file";
      fileInput.accept   = ".docx";
      fileInput.multiple = true;
      fileInput.style.display = "none";

      document.body.appendChild(fileInput);
      fileInput.click();

      fileInput.addEventListener("change", async function (event) {
        const files = Array.from(event.target.files);
        document.body.removeChild(fileInput);

        if (files.length === 0) return;

        statusIcon.style.display = "flex";
        statusIcon.style.alignItems = "center";
        const spinner   = statusIcon.querySelector('.loading-spinner');
        const checkmark = statusIcon.querySelector('.success-check');
        const cross     = statusIcon.querySelector('.error-cross');

        // Create or reset progress text
        const totalFiles   = files.length;
        let successCount   = 0;
        let failureCount   = 0;
        let progressText   = statusIcon.querySelector('.progress-text');
        if (!progressText) {
          progressText = document.createElement('span');
          progressText.className = 'progress-text';
          statusIcon.appendChild(progressText);
        }
        progressText.innerText = `0/${totalFiles}`;

        // reset visuals
        spinner.style.display   = "block";
        checkmark.classList.remove('show');
        cross.classList.remove('show');

        // Upload files one by one
        for (const file of files) {
          try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("collection_name", selectedGroup);
            const sessionCookie = document.cookie
              .split("; ")
              .find((row) => row.startsWith("chainlit_session="));
            if (sessionCookie) {
              fd.append("session_id", sessionCookie.split("=")[1]);
            }

            const res  = await fetch("/api/upload-milvus", {
              method:      "POST",
              credentials: "include",
              body:         fd,
            });
            const data = await res.json();

            if (data.success) {
              successCount++;
            } else {
              failureCount++;
            }
          } catch (err) {
            console.error("Upload error:", err);
            failureCount++;
          }

          // update the “X/Y” text after each attempt
          progressText.innerText = `${successCount}/${totalFiles}`;

          // small pause so user can see updates
          await new Promise(r => setTimeout(r, 300));
        }

        // Once all done: hide spinner and show final icon
        spinner.style.display = "none";
        if (failureCount === 0) {
          checkmark.style.animation = "checkmark-pop 0.3s ease-out forwards";
          checkmark.classList.add('show');
        } else {
          cross.style.animation = "cross-pop 0.3s ease-out forwards";
          cross.classList.add('show');
        }

        // Clean up after 2 seconds
        setTimeout(() => {
          statusIcon.style.display = "none";
          progressText.remove();
          checkmark.classList.remove('show');
          cross.classList.remove('show');
          checkmark.style.animation = "";
          cross.style.animation = "";
          spinner.style.display = "block";
        }, 2000);
      });
    }

    function addUploadButton() {
      const header = document.getElementById("header");
      if (!header) return;
      if (document.getElementById("upload-button-container")) return;

      // Create a container with flex layout.
      const container = document.createElement("div");
      container.id             = "upload-button-container";
      container.style.display  = "flex";
      container.style.alignItems = "center";
      container.style.marginRight = "10px";
      container.style.gap      = "8px";

      // Create the status icon container
      const statusIcon = document.createElement("div");
      statusIcon.id     = "upload-status-icon";
      statusIcon.style.display = "none";
      statusIcon.innerHTML = `
        <div class="status-container" style="position: relative; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;">
          <style>
            .loading-spinner {
              position: absolute;
              width: 100%;
              height: 100%;
              border: 2px solid transparent;
              border-color: #e0e0e0;
              border-top-color: #3b82f6;
              border-radius: 50%;
              animation: spinner 0.8s cubic-bezier(0.5, 0, 0.5, 1) infinite;
            }
            .success-check, .error-cross {
              position: absolute;
              font-size: 20px;
              opacity: 0;
              transform: scale(0.5);
              transition: all 0.3s ease-out;
            }
            .success-check { color: #22c55e; }
            .error-cross    { color: #ef4444; }
            .success-check.show, .error-cross.show {
              opacity: 1;
              transform: scale(1);
            }
            @keyframes spinner {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
            @keyframes checkmark-pop {
              0% { transform: scale(0.5); opacity: 0; }
              70% { transform: scale(1.2); opacity: 0.7; }
              100% { transform: scale(1); opacity: 1; }
            }
            @keyframes cross-pop {
              0% { transform: scale(0.5); opacity: 0; }
              70% { transform: scale(1.2); opacity: 0.7; }
              100% { transform: scale(1); opacity: 1; }
            }
            /* New: circle badge for file-count */
            .progress-text {
              display: flex;
              align-items: center;
              justify-content: center;
              width: 24px;
              height: 24px;
              margin-left: 8px;
              border-radius: 50%;
              background-color: #3b82f6;
              color: white;
              font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
              font-size: 0.75rem;
              font-weight: 500;
            }
          </style>
          <div class="loading-spinner"></div>
          <div class="success-check">✓</div>
          <div class="error-cross">✗</div>
        </div>
      `;

      // Create the upload button.
      const uploadButton = document.createElement("button");
      uploadButton.id         = "upload-document-button";
      uploadButton.innerText  = "Upload DOCX";
      uploadButton.className  =
        "inline-flex items-center px-4 py-2 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none border border-gray-300 shadow-sm";
      uploadButton.style.cursor = "pointer";

      uploadButton.addEventListener("click", function () {
        const existing = document.getElementById("user-group-dropdown");
        if (existing) existing.remove();

        const select = document.createElement("select");
        select.id    = "user-group-dropdown";
        select.style.marginLeft = "8px";

        const placeholder = document.createElement("option");
        placeholder.value       = "";
        placeholder.textContent = "Select organization...";
        placeholder.disabled    = true;
        placeholder.selected    = true;
        select.appendChild(placeholder);

        filteredGroups.forEach(group => {
          const opt = document.createElement("option");
          opt.value       = group;
          opt.textContent = group;
          select.appendChild(opt);
        });

        uploadButton.parentNode.insertBefore(select, uploadButton.nextSibling);
        select.focus();

        select.addEventListener("change", function () {
          triggerFileInput(select.value, statusIcon);
          select.remove();
        });
      });

      container.appendChild(statusIcon);
      container.appendChild(uploadButton);

      const readmeButton = document.getElementById("readme-button");
      if (readmeButton) {
        readmeButton.parentNode.insertBefore(container, readmeButton);
      } else {
        header.appendChild(container);
      }
    }

    // Observe and insert
    const uploadObserver = new MutationObserver(() => addUploadButton());
    uploadObserver.observe(document.body, { childList: true, subtree: true });

    // Initial insert
    addUploadButton();
  } else {
    console.log("User is not pod_admin; skipping upload button.");
  }
});
