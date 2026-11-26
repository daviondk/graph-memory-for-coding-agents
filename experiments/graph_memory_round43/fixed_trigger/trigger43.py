"""An online trigger. The input needs no length, terminal statistics or lookahead."""
def cut(messages):
    pending=set();seen=set();groups=0;prefix=[]
    for message in messages:
        prefix.append(message)
        if message["role"]=="assistant":
            for call in message.get("tool_calls",()):
                key=call["id"]
                if key in seen:raise ValueError("repeated call identifier")
                seen.add(key);pending.add(key)
        elif message["role"]=="tool":
            key=message["tool_call_id"]
            if key not in pending:raise ValueError("unmatched tool response")
            pending.remove(key)
            if not pending:
                groups+=1
                if groups==8:return prefix,groups,len(seen)
    if pending:raise ValueError("unterminated observed group")
    return None,groups,len(seen)


def record(t,messages,calls):
    return dict(status="as-of",session_id=t,source_intent_count=1,source_intent_ids=["as-of"],
        source_intents=[dict(intent_id="as-of",natural_language_intent="as-of")],
        session_finalized_by_intent_id="as-of",total_steps=calls,enable_thinking=False,
        messages=messages,tools=[],final_output="",intent_id="as-of",metadata={})
