import { useRef } from "react";

export default function GroupsDropdown() {
  // Retrieve the groups passed from Python via props
  const groups = props.groups || [];
  // Create a ref for the hidden file input element
  const fileInputRef = useRef(null);

  // Handler to trigger the file input when the button is clicked
  const handleUploadClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  // Handler for file selection and uploading the file
  const handleFileChange = (event) => {
    const files = event.target.files;
    if (files.length > 0) {
      const file = files[0];
      console.log("Uploading file:", file.name);
      const formData = new FormData();
      formData.append("file", file);
      // Adjust the endpoint and error handling as needed
      fetch("/api/upload-milvus", {
        method: "POST",
        body: formData,
      })
        .then((response) => response.json())
        .then((data) => {
          console.log("Upload successful:", data);
          alert("File uploaded successfully!");
        })
        .catch((error) => {
          console.error("Upload failed:", error);
          alert("File upload failed!");
        });
    }
  };

  return (
    <div className="my-4">
      <label htmlFor="groups-dropdown" className="block mb-2 text-sm font-medium text-gray-700">
        Your Groups
      </label>
      <div className="flex items-center gap-4">
        {/* Dropdown */}
        <select
          id="groups-dropdown"
          className="bg-white border border-gray-300 rounded-md px-3 py-2 h-10"
          defaultValue={groups.length > 0 ? groups[0] : ""}
        >
          {groups.map((group, index) => (
            <option key={index} value={group}>
              {group}
            </option>
          ))}
        </select>

        {/* Upload Button (Only for pod_admin users) */}
        {groups.includes("pod_admin") && (
          <>
            <button
              onClick={handleUploadClick}
              className="px-4 py-2 h-10 text-sm font-medium rounded-md flex items-center"
              style={{
                backgroundColor: "#1d4ed8",
                color: "white",
                border: "1px solid #1e40af",
              }}
            >
              Upload Document to Milvus
            </button>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: "none" }}
              accept=".pdf,.docx,.txt"
              onChange={handleFileChange}
            />
          </>
        )}
      </div>
    </div>
  );
}
