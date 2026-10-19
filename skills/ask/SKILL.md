---
name: ask
description: Use when the user asks to be interviewed, wants guided choices, or needs to answer a question before work can continue. Ask through the agent's user-question tool.
---

# Ask

Use the built-in user-question tool when you need input from the user.

- Claude Code: use `AskUserQuestion` when available.
- Codex: use `request_user_input` or `request_user_input_async` when available and allowed in the current mode.
- Follow the tool's rules. If no question tool is available or allowed, ask a short question in chat.
- Ask only what changes the next decision. Do not ask for facts you can check yourself.
- Keep questions short. Offer clear choices when useful, with a recommended choice and its tradeoff.
- Group related questions. Avoid long forms and repeated questions.
- Wait for required answers before doing work that depends on them. Continue other useful work when possible.
- Use the answer. Do not ask again for a choice the user already made.
