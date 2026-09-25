"""
One call_model() entry point across providers, so runner.py and judge.py
don't need to know which SDK a given model uses.
"""

from config import resolve_credentials


def call_model(model_cfg: dict, system: str, user: str, temperature: float = 0.0) -> str:
    provider = model_cfg["provider"]
    creds = resolve_credentials(model_cfg)

    if provider == "azure_openai":
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=creds.get("api_key", ""),
            azure_endpoint=creds.get("endpoint", ""),
            api_version=creds.get("api_version", "2024-10-21"),
        )
        resp = client.chat.completions.create(
            model=model_cfg["deployment"],
            temperature=temperature,
            messages=[{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=creds.get("api_key", ""))
        # GPT-5 models reject any temperature but the default (1), so it's
        # only sent to older models.
        extra = {} if model_cfg["model"].startswith("gpt-5") else {"temperature": temperature}
        resp = client.chat.completions.create(
            model=model_cfg["model"],
            messages=[{"role": "system", "content": system},
                     {"role": "user", "content": user}],
            **extra,
        )
        return resp.choices[0].message.content or ""

    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=creds.get("api_key", ""))
        resp = client.messages.create(
            model=model_cfg["model"],
            max_tokens=2048,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    if provider == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=creds.get("api_key", ""))
        resp = client.models.generate_content(
            model=model_cfg["model"],
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=temperature,
            ),
        )
        return resp.text or ""

    if provider == "together":
        from openai import OpenAI

        client = OpenAI(api_key=creds.get("api_key", ""),
                        base_url="https://api.together.xyz/v1")
        resp = client.chat.completions.create(
            model=model_cfg["model"],
            temperature=temperature,
            messages=[{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    raise ValueError(f"Unknown provider: {provider!r} (model {model_cfg.get('name')})")
