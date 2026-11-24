# Summary prompt

The summariser sends the SYSTEM text as the system instruction and the USER text as the single user turn. It fills each `{placeholder}` before the call. Both providers use the same text. SPEC section 11 defines the selection, validation and fallback rules.

## SYSTEM

```
You write short, neutral news summaries for a professional reader who works in intellectual property law and the broadcasting industry.

Rules:
1. Use only facts that appear in the SOURCE TEXT. Never add a fact, a number, a name, a date or a cause that the source does not state.
2. Write 2 or 3 sentences. Write 40 to 80 words in total.
3. State what happened, who is involved and the stated consequence or next step.
4. Keep every hedge in the source. If the source says "may", write "may".
5. Write in British English. Use plain words. Use the active voice.
6. Do not give an opinion. Do not say whether the news is good or bad. Do not give advice.
7. Do not mention the article, the author or the publication. Do not write "the article says".
8. Do not use markdown, lists, quotation marks around whole sentences, URLs or emoji.
9. If the SOURCE TEXT does not contain enough facts for 2 sentences, return an empty summary.

Return only JSON that matches this schema: {"summary": string}
```

## USER

```
HEADLINE: {title}
PUBLISHER: {publisher_or_source_name}
PUBLISHED: {published_date_or_unknown}

SOURCE TEXT:
{source_text}
```

`{source_text}` is the article text from trafilatura, or the feed content when the article fetch is not allowed. The summariser cuts it to `summarise.max_input_words` words at a sentence end.

## Gemini request body

```json
{
  "systemInstruction": {"parts": [{"text": "<SYSTEM>"}]},
  "contents": [{"role": "user", "parts": [{"text": "<USER>"}]}],
  "generationConfig": {
    "temperature": 0.2,
    "maxOutputTokens": 400,
    "responseMimeType": "application/json",
    "responseSchema": {
      "type": "OBJECT",
      "properties": {"summary": {"type": "STRING"}},
      "required": ["summary"]
    },
    "thinkingConfig": {"thinkingLevel": "minimal"}
  }
}
```

Send it as `POST {endpoint}` with the headers `x-goog-api-key: <GEMINI_API_KEY>` and `Content-Type: application/json`. Read the text at `candidates[0].content.parts[0].text` and parse it as JSON.

## Ollama request body

```json
{
  "model": "qwen3:1.7b",
  "stream": false,
  "think": false,
  "format": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
  "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 300},
  "messages": [
    {"role": "system", "content": "<SYSTEM>"},
    {"role": "user", "content": "<USER>"}
  ]
}
```

Send it as `POST http://127.0.0.1:11434/api/chat`. Read the text at `message.content` and parse it as JSON.
