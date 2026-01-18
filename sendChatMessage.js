/**
 * Sends a chat message to the robotics tutor bot.
 * Handles session management via cookies and extracts context/images from the iframe.
 * * @param {string} message - The user's question or message.
 * @returns {Promise<Object>} - The JSON response from the server.
 */
async function sendChatMessage(message) {
    // --- Helper Functions for Cookies ---
    const getCookie = (name) => {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    };

    const setCookie = (name, value, days) => {
        let expires = "";
        if (days) {
            const date = new Date();
            date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
            expires = "; expires=" + date.toUTCString();
        }
        document.cookie = name + "=" + (value || "") + expires + "; path=/";
    };

    // --- 1. Session Management ---
    let sessionId = getCookie("session_id");
    
    if (!sessionId) {
        // Generate a new UUID if one doesn't exist
        // crypto.randomUUID() is available in most modern browsers (secure contexts)
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            sessionId = crypto.randomUUID();
        } else {
            // Fallback for environments where crypto.randomUUID isn't available
            sessionId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        }
        
        // Store for 7 days
        setCookie("session_id", sessionId, 7); 
        console.log("Generated and stored new session_id:", sessionId);
    } else {
        console.log("Using existing session_id from cookie:", sessionId);
    }

    // --- 2. Get the content ---
    const iframe = document.getElementById("contentFrame");
    if (!iframe) {
        console.error("Iframe 'contentFrame' not found.");
        return;
    }

    // Ensure we access the document correctly. 
    // Note: This requires the iframe to be on the same origin.
    const iframeDoc = iframe.contentWindow ? iframe.contentWindow.document : iframe.contentDocument;
    
    // Check if the iframe has loaded content
    if (!iframeDoc || !iframeDoc.body) {
        console.error("Iframe content not accessible or not loaded.");
        return;
    }

    const iframeContent = iframeDoc.body.getElementsByClassName("container")[0];
    
    if (!iframeContent) {
        console.error("Container element not found in iframe.");
        return;
    }
  
    // --- 3. Helper function to extract and convert images to Base64 ---
    const extractImages = async (container) => {
      // Find all image tags in the container.
      const imgs = Array.from(container.getElementsByTagName('img'));
      
      const imagePromises = imgs.map(async (img, idx) => {
        try {
          const src = img.src;
          let base64Data = "";
          let name = `image_${idx}`;
  
          // Check if it's already a data URL
          if (src.startsWith('data:')) {
            // Remove the prefix (e.g., "data:image/png;base64,") to get raw base64
            base64Data = src.split(',')[1];
          } else {
            // If it's a URL, fetch it and convert to blob
            const response = await fetch(src);
            const blob = await response.blob();
            
            // Convert Blob to Base64
            base64Data = await new Promise((resolve, reject) => {
              const reader = new FileReader();
              reader.onloadend = () => {
                  // split(',') to remove the data:MIME;base64, prefix
                  const result = reader.result;
                  resolve(result.split(',')[1]); 
              };
              reader.onerror = reject;
              reader.readAsDataURL(blob);
            });
            
            // Try to extract a filename from the URL to help the LLM identify it
            const urlParts = src.split('/');
            const fileName = urlParts[urlParts.length - 1];
            if (fileName) name = fileName;
          }
          
          return {
            name: name,
            data: base64Data
          };
        } catch (e) {
          console.warn(`Skipping image ${img.src} due to error:`, e);
          return null;
        }
      });
  
      // Wait for all images to process and filter out any failures
      const results = await Promise.all(imagePromises);
      return results.filter(item => item !== null);
    };
  
    // --- 4. Process the images ---
    const imagesList = await extractImages(iframeContent);
    console.log(`Extracted ${imagesList.length} images.`);
  
    // --- 5. Construct Payload ---
    const payload = {
      session_id: sessionId,
      context: iframeContent.innerHTML, 
      message: message, // Use the passed message argument
      images: imagesList 
    };
  
    // --- 6. Send Request ---
    return fetch('https://robotics-tutorialbot.onrender.com/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(response => response.json())
    .then(data => {
        console.log("Server Response:", data);
        return data;
    })
    .catch(error => {
        console.error('Error:', error);
        throw error;
    });
}