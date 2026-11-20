"""Wire-level integration test through the pinned agent's real LiteLLM adapter."""
import argparse
import json
from pathlib import Path

from minisweagent.models.litellm_model import LitellmModel


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--out",type=Path,required=True)
    cli.add_argument("--api-base",default="http://127.0.0.1:18991/replicate/0/v1")
    cli.add_argument("--model",default="openai/Qwen/Qwen3-8B")
    args=cli.parse_args()
    adapter=LitellmModel(model_name=args.model,cost_tracking="ignore_errors",
        observation_template="<returncode>{{output.returncode}}</returncode>\n<output>{{output.output}}</output>",
        model_kwargs=dict(api_base=args.api_base,api_key="local",
                          temperature=.5,parallel_tool_calls=True,drop_params=True,max_tokens=128))
    messages=[dict(role="system",content="You are a shell assistant. Use the bash tool."),
              dict(role="user",content="First use bash to run exactly 'printf FIRST'. Once the tool reports FIRST, use bash to run 'printf SECOND'.")]
    first=adapter.query(messages)
    a=first["extra"]["actions"][0]
    assert "FIRST" in a["command"]
    observations=adapter.format_observation_messages(first,[dict(output="FIRST",returncode=0)])
    assert observations[0]["role"]=="tool" and observations[0]["tool_call_id"]==a["tool_call_id"]
    second=adapter.query([*messages,first,*observations])
    assert "SECOND" in second["extra"]["actions"][0]["command"]
    args.out.write_text(json.dumps(dict(first=first,observations=observations,second=second),indent=2),encoding="utf-8")
    print("verified",a["command"],second["extra"]["actions"][0]["command"],flush=True)


if __name__=="__main__":
    main()
