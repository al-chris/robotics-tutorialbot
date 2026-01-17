
content = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Tutor</title>

    <!-- Math Rendering -->
    <link rel="stylesheet" href="tutorial/katex/katex.min.css">
    <script src="tutorial/katex/katex.min.js"></script>
    <script src="tutorial/katex/contrib/auto-render.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

    <style>
        body {
            background-color: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Segoe UI', 'Inter', sans-serif;
            display: flex;
            flex-direction: column;
            height: 100vh;
            margin: 0;
            overflow: hidden;
        }

        #chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #424242; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #4f4f4f; }

        .message {
            max-width: 90%;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.95em;
            line-height: 1.5;
            word-wrap: break-word;
        }

        .user-message {
            background-color: #264f78;
            align-self: flex-end;
            margin-left:auto;
            border-bottom-right-radius: 2px;
        }

        .bot-message {
            background-color: #2d2d2d;
            border: 1px solid #3e3e3e;
            align-self: flex-start;
            border-bottom-left-radius: 2px;
        }

        .system-message {
            align-self: center;
            font-size: 0.8em;
            color: #888;
            font-style: italic;
            margin: 5px 0;
        }

        .input-area {
            background-color: #252526;
            padding: 15px;
            display: flex;
            gap: 10px;
            border-top: 1px solid #3e3e3e;
        }

        #userInput {
            flex: 1;
            background-color: #3c3c3c;
            border: 1px solid #3c3c3c;
            color: white;
            padding: 10px;
            border-radius: 4px;
            resize: none;
            font-family: inherit;
            height: 48px; /* Two linesish */
        }

        #userInput:focus { outline: 1px solid #007fd4; }

        button {
            background-color: #0e639c;
            color: white;
            border: none;
            padding: 0 20px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
        }
        button:hover { background-color: #1177bb; }
        button:disabled { background-color: #444; cursor: default; }

        /* Typeset Math */
        .katex { font-size: 1.1em !important; }
        
        /* Markdown generated content */
        .bot-message p { margin: 0 0 10px; }
        .bot-message p:last-child { margin: 0; }
        .bot-message code { background: #101010; padding: 2px 5px; border-radius: 3px; font-family: monospace; }
        .bot-message pre { background: #101010; padding: 10px; border-radius: 5px; overflow-x: auto; margin: 10px 0; }
        .bot-message img { max-width: 100%; border-radius: 4px; margin-top: 5px; }
    </style>
</head>
<body>

    <div id="chat-container">
        <div class="message bot-message">
            Hello! I'm your Robotics AI Tutor. Ask me anything about the current section.
        </div>
    </div>

    <div class="input-area">
        <textarea id="userInput" placeholder="Ask a question about this page..."></textarea>
        <button id="sendBtn" onclick="sendMessage()">Send</button>
    </div>

    <script>
        const chatContainer = document.getElementById('chat-container');
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        
        // --- CONFIGURATION ---
        const SERVER_URL = 'http://localhost:8000/chat';
        const SESSION_KEY = 'mentor_session_token';

        // --- STATE ---
        let currentSectionId = "2.1"; // Default/Fallback
        let sessionToken = localStorage.getItem(SESSION_KEY);

        // --- 1. INITIALIZATION ---
        if (!sessionToken) {
            // Generate simple UUIDv4-like token
            sessionToken = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
            localStorage.setItem(SESSION_KEY, sessionToken);
        }
        console.log("Session:", sessionToken);

        // --- 2. SECTION DETECTION (Fallback Strategy) ---
        // Try to read parent's hash on load to determine section
        try {
            if (window.parent && window.parent.location.hash) {
                updateSectionFromHash(window.parent.location.hash);
            }
        } catch (e) {
            console.log("Cannot read parent hash (likely blocked or standalone). Using default.");
        }

        // Poll for hash changes (fallback if no postMessage)
        setInterval(() => {
            try {
                if (window.parent && window.parent.location.hash) {
                    updateSectionFromHash(window.parent.location.hash);
                }
            } catch(e) {}
        }, 2000);

        function updateSectionFromHash(hash) {
            // Expected format: #tutorial/pages/section_2_1.html
            // Extract: 2_1 -> 2.1
            const match = hash.match(/section_(\d+(?:_\d+)*)/);
            if (match && match[1]) {
                const newId = match[1].replace(/_/g, '.');
                if (newId !== currentSectionId) {
                    currentSectionId = newId;
                    addSystemMessage(`Context switched to Section ${currentSectionId}`);
                }
            }
        }

        // --- 3. EVENT LISTENER (For Native Integration) ---
        window.addEventListener('message', (event) => {
            if (event.data && event.data.type === 'setSection') {
                const newSection = event.data.sectionId;
                if(newSection !== currentSectionId) {
                    currentSectionId = newSection;
                    addSystemMessage(`Context switched to Section ${currentSectionId}`);
                }
            }
        });

        // --- 4. IMAGE SCRAPING ---
        function getContextImages() {
            let images = [];
            try {
                // Try to find the content frame in the parent
                if (window.parent && window.parent.document) {
                    const contentFrame = window.parent.document.getElementById('contentFrame');
                    if (contentFrame && contentFrame.contentDocument) {
                        const imgs = contentFrame.contentDocument.querySelectorAll('img');
                        imgs.forEach(img => {
                            // Convert to base64
                            try {
                                const canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                                if (canvas.width < 50 || canvas.height < 50) return;

                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0);
                                const dataURL = canvas.toDataURL('image/png');
                                
                                const filename = img.src.split('/').pop() || "image.png";

                                images.push({
                                    name: filename,
                                    data: dataURL.replace(/^data:image\/(png|jpg|jpeg);base64,/, "")
                                });
                            } catch (err) {
                                console.warn("Failed to capture image:", err);
                            }
                        });
                    }
                }
            } catch (e) {
                console.warn("Could not access content frame images (Cross-Origin?):", e);
            }
            return images;
        }

        // --- 5. UI HELPERS ---
        function addMessage(text, type) {
            const div = document.createElement('div');
            div.className = `message ${type}`;
            
            if (type === 'bot-message') {
                if (typeof marked !== 'undefined') {
                    div.innerHTML = marked.parse(text);
                } else {
                    div.textContent = text;
                }
                
                if (typeof renderMathInElement !== 'undefined') {
                    renderMathInElement(div, {
                        delimiters: [
                            {left: "$$", right: "$$", display: true},
                            {left: "$", right: "$", display: false}
                        ]
                    });
                }
            } else {
                div.textContent = text; 
            }

            chatContainer.appendChild(div);
            scrollToBottom();
        }

        function addSystemMessage(text) {
            const div = document.createElement('div');
            div.className = 'system-message';
            div.textContent = text;
            chatContainer.appendChild(div);
            scrollToBottom();
        }

        function scrollToBottom() {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        // --- 6. SEND LOGIC ---
        async function sendMessage() {
            const text = userInput.value.trim();
            if (!text) return;

            addMessage(text, 'user-message');
            userInput.value = '';
            
            sendBtn.disabled = true;
            userInput.disabled = true;

            const payload = {
                session_id: sessionToken,
                section_id: currentSectionId,
                message: text,
                images: getContextImages()
            };

            try {
                const response = await fetch(SERVER_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    throw new Error(`Server status: ${response.status}`);
                }
                
                const data = await response.json();
                addMessage(data.reply || "(No response)", 'bot-message');

            } catch (err) {
                console.error("Chat Error:", err);
                addSystemMessage("Error: Could not connect to backend server.");
            } finally {
                sendBtn.disabled = false;
                userInput.disabled = false;
                userInput.focus();
            }
        }

        // --- 7. INPUT LISTENERS ---
        userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
    </script>
</body>
</html>
"""

import os
# Write to the file in the parent directory of backend (which is the root)
chat_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chat.html")
with open(chat_file, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Successfully overwrote {chat_file}")
