Okay, let's see. The user wants a skill that rewrites text to be shorter while preserving meaning. The skill needs to be generalizable, not hard-coded to this specific prompt.

First, I need to create a class that subclasses Skill. The fields required are id, name, description, tags, inputs, outputs. The origin should be "self_written".

The id should be in snake_case. Maybe something like "text_shorten". The name could be "Shorten Text". Description: "Rewrites text to be shorter while preserving meaning". Tags: maybe ["text", "shorten", "summarize", "concise"].

Inputs: the user probably needs to provide the text to shorten. So inputs should be a dict with a key like "text" (string). Outputs should be a dict with a key like "shortened_text" (string).

The execute method needs to take ctx and inputs. It should handle missing inputs gracefully. So use .get with defaults. For example, if the input text is missing, maybe set a default like an empty string.

The method will call llm_complete. The system prompt should guide the LLM to shorten the text without losing meaning. The prompt might be something like: "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

Wait, the user wants to preserve meaning, so the LLM should focus on conciseness. Also, the output should be just the shortened text, no extra stuff.

So the prompt for llm_complete would be: "Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text: {text}"

Wait, but the inputs are in a dict. So in the execute method, get the text from inputs. If it's missing, maybe set to empty string.

Wait, the problem says handle missing inputs gracefully. So in the execute method, inputs.get('text', '').

Then call llm_complete with system prompt that tells the L: "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text: {text}"

Wait, but the system prompt should be a string that the LLM uses. So maybe the system is "You are a text summarizer..." and the prompt is the user's input.

Wait, the llm_complete function takes system, prompt, max_tokens. So the system is the role, and the prompt is the actual input to the LLM.

Wait, the parameters for llm_complete are: system (string), prompt (string), max_tokens (int). So the system is the system message, and the prompt is the user's message.

So in this case, the system message could be "You are a text summarizer. Your task is to rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text." Then the prompt would be the text input.

Wait, but the user's input to the LLM is the text to shorten. So the prompt for the LLM is the text to process.

Wait, maybe the system message is the instruction, and the prompt is the text to process.

So the system message would be: "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

Then the prompt is the text input from the user.

Wait, but in the llm_complete function, the prompt is the actual input to the LLM. So the system message is the role, and the prompt is the user's message.

Wait, perhaps the system is the role description, and the prompt is the actual text to process.

Wait, maybe the system message is the instruction, and the prompt is the text.

Wait, I'm a bit confused here. Let me think.

The llm_complete function's documentation says: "llm_complete(ctx, system=..., prompt=..., max_tokens=...)". So system is the system message (like the role), prompt is the user's message.

So for this task, the system message would be a string that sets the role, like "You are a text summarizer..." and the prompt would be the text input.

Wait, but in this case, the user's input to the LLM is the text to shorten. So the prompt for the LLM is the text input.

Wait, no. The system message is the instruction for the LLM. For example, in a chat, the system message is the role, and the user message is the input.

So here, the system message would be: "You are a text summarizer. Your task is to rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

The prompt would be the actual text that needs to be shortened.

Wait, but in the context of this skill, the inputs are the text to process. So the prompt for the LLM is the text input.

Wait, perhaps the system message is the instruction, and the prompt is the text.

So the code would be:

In execute method:

text = inputs.get('text', '')

system = "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

prompt = f"Text to shorten: {text}"

Then call llm_complete with system, prompt, max_tokens=200.

Wait, but the prompt should be the text to process. Maybe the system message is the instruction, and the prompt is the text.

Wait, perhaps the prompt for the LLM is just the text, but the system message guides the LLM.

Alternatively, the system message could be the instruction, and the prompt is the text.

Wait, maybe the system message is the role, and the prompt is the text.

So the system message is: "You are a text summarizer. Your task is to rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

The prompt is the text input.

But the LLM might need to be told what to do. So the system message is the instruction, and the prompt is the text.

Wait, but in some cases, the prompt is the user's message, so here the user's message is the text to process.

Hmm. Let's try to structure it.

The LLM should be told to take the text and output a shorter version. So the system message is the instruction, and the prompt is the text.

Wait, perhaps the system message is the instruction, and the prompt is the text.

So in code:

system = "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

prompt = inputs.get('text', '')

Wait, but the prompt should be the text to process. So the prompt is the text.

Wait, but the LLM might need to be told to process the text. So the prompt could be "Text to shorten: {text}".

But the problem says to preserve meaning, so the LLM should output the shortened text.

So the code would be:

text = inputs.get('text', '')

system = "You are a text summarizer. Your task is to rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

prompt = f"Text to shorten: {text}"

max_tokens = 200

Then the output of llm_complete is the shortened text.

Wait, but the LLM might output the text with the instruction, but the system message says "Only output the shortened text", so it should be okay.

Wait, the system message says "Only output the shortened text", so the LLM should not add anything else.

So the prompt for the LLM is the text to process.

Wait, perhaps the prompt is just the text. Let's see.

The user's input to the LLM is the text to shorten. So the prompt is the text.

But the system message guides the LLM.

So the code would be:

system = "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

prompt = text

But the LLM might need to be told that the text is to be processed.

Hmm. Maybe the prompt is the text, and the system message is the instruction.

So the llm_complete call is:

llm_complete(ctx, system=system, prompt=text, max_tokens=200)

Then the output is the shortened text.

Wait, but the problem says the output should be a dict matching the outputs. So the output is {"shortened_text": llm_output}

But the LLM might output the text, so the output is that.

Wait, the code in execute:

text = inputs.get('text', '')

system = "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."

prompt = text

result = llm_complete(ctx, system=system, prompt=prompt, max_tokens=200)

Then return {"shortened_text": result}

Wait, but the LLM might output with extra spaces or newlines. But the system message says "Only output the shortened text", so it should be okay.

Wait, but the problem says "Handle missing inputs gracefully". So if text is missing, use empty string.

So the code would be:

def execute(self, ctx: SkillContext, inputs: dict) -> dict:
    text = inputs.get('text', '')
    system = "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."
    prompt = text
    result = llm_complete(ctx, system=system, prompt=prompt, max_tokens=200)
    return {"shortened_text": result}

Wait, but the max_tokens is 200. Maybe that's a good default.

Wait, the problem says the skill should be generalizable. So it's not hard-coded to this prompt. The system message is fixed, but the prompt is the text input.

Yes, this should work.

Let me check the invariants.

Exactly one class, subclassing Skill.

Fields: id (snake_case), name, description, tags: list[str], inputs: dict[str,str], outputs: dict[str,str]

origin = "self_written"

Method execute.

Imports only from nexus.skills.base.

No filesystem writes, etc.

So the class:

class TextShorten(Skill):
    id = "text_shorten"
    name = "Shorten Text"
    description = "Rewrites text to be shorter while preserving meaning"
    tags = ["text", "shorten", "summarize", "concise"]
    inputs = {"text": "Text to shorten"}
    outputs = {"shortened_text": "Shortened text"}
    origin = "self_written"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        text = inputs.get('text', '')
        system = "You are a text summarizer. Rewrite the following text to be shorter while preserving its meaning. Do not add new information. Only output the shortened text."
        result = llm_complete(ctx, system=system, prompt=text, max_tokens=200)
        return {"shortened_text": result}

Wait, but the outputs dict should have the keys as strings. The outputs is {"shortened_text": "Shortened text"}, which is correct.

The inputs is a dict with key "text" and description "Text to shorten".

Yes.

The tags are a list of strings.

The origin is "self_written".

This should meet all the invariants.

Wait, the problem says "the skill should be generalizable (not hard-coded to