To understand how [Claude](https://www.google.com/search?q=claude&kgmid=/g/11kq5ghr35) "remembers" something, you have to look at it in two ways: short-term memory (inside a single chat) and long-term memory (across different chats). [1, 2] 
Large Language Models (LLMs) like Claude do not have a biological brain that changes or holds a permanent internal state. Instead, Claude remembers using a "Read/Write" system prompt loop. [2, 3] 
------------------------------
## 1. Short-Term Memory: The Context Window
When you are inside a single chat thread, Claude has an incredibly powerful, near-perfect memory. [1] 

* The "Scrollback" Illusion: Claude does not actually look at a static page of text. Every single time you press send, your entire conversation history—all your past prompts, Claude’s past answers, and uploaded files—is bundled together and sent back to Claude all at once. [1, 4] 
* The Context Limit: This text bundle is loaded into Claude's Context Window, which can hold massive amounts of text (equal to a 400-page novel). Claude "remembers" details from hours ago simply because it reads the entire transcript again with every new prompt. [1] 

------------------------------
## 2. Long-Term Cross-Session Memory: The "Read/Write" Loop
When you open a brand new chat, the short-term window resets to zero. To remember your preferences or project details across different chats, Claude uses an automated text-updating system: [1, 3, 5] 
## Step 1: Writing (The Extraction)
As you talk, Claude actively looks for facts worth saving (e.g., "I am a Python developer," "My brand voice is casual," or "The deadline moved to Friday"). [5, 6] 

* Automated: Instead of summarizing the whole chat when you close it, Claude triggers a hidden background action to extract specific topics mid-conversation.
* Manual: You can explicitly tell it, "Claude, remember that I hate using semicolons," and it will instantly save it. [5] 

## Step 2: Storing (The Profile)
Claude saves these facts as a bulleted text profile. [5, 6] 

* On the web/mobile app, this is securely saved to your Anthropic account cloud profile.
* On developer tools like Claude Code, it is written directly to a local Markdown file (memory.md) on your computer. [5, 7] 

## Step 3: Reading (The Injection)
When you start a brand new chat, before you even type your first letter, the system automatically pulls that text profile out of storage. It silently injects those saved bullet points into the very top of Claude's context window (hidden behind your screen). [2, 3] 
Because those facts are pinned to the top of the new conversation, Claude treats them as baseline facts and acts like it "remembered" you from yesterday. [2, 8] 
------------------------------
## 3. The "Dream" Cycle (Memory Maintenance)
To prevent its memory from getting messy, overloaded, or filled with old information, Claude relies on periodic synthesis. Every 24 hours (or through commands like /dream in developer tools), a background process reviews the stored notes. It deletes duplicate entries, updates old deadlines, and condenses sentences to keep the memory profile short, clean, and highly accurate. [5, 7, 9, 10] 
Would you like to see what your current saved memory profile looks like, or would you like to know how to manually edit/delete a fact Claude has stored about you? [5, 11] 

[1] [https://medium.com](https://medium.com/@abirami.k/the-hidden-architecture-how-claude-remembers-everything-and-when-it-forgets-5fa54b3e6f97)
[2] [https://www.youtube.com](https://www.youtube.com/watch?v=F6BSULfdGWE&t=144)
[3] [https://joseparreogarcia.substack.com](https://joseparreogarcia.substack.com/p/claude-code-memory-explained)
[4] [https://www.youtube.com](https://www.youtube.com/watch?v=YL8KsWTlCKI&t=135)
[5] [https://support.claude.com](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context)
[6] [https://www.aicodex.to](https://www.aicodex.to/articles/claude-memory-practical)
[7] [https://www.youtube.com](https://www.youtube.com/watch?v=2EboW-zYn6U&t=473)
[8] [https://unabyss.com](https://unabyss.com/blog/claude-memory-feature)
[9] [https://www.youtube.com](https://www.youtube.com/watch?v=rsuU_ueV0fo&t=28)
[10] [https://www.youtube.com](https://www.youtube.com/watch?v=T9-i5AEX21Q&t=74)
[11] [https://www.youtube.com](https://www.youtube.com/watch?v=DTKMhKkij-s&t=295)
