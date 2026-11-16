"""A Claude Code stand-in for the driver's edge cases (tests/test_agent_edges.py): FAKE_MODE=startcrash
fails its first start and refuses --resume of a session it never saved; a "nonobj" turn writes a JSON
line that is not an object; a "cancelask" turn asks, withdraws the question and goes on; a "fail" turn
ends in an error result. FAKE_LOG: each start's argv and each prompt are written there; FAKE_MODE=atcrash
dies at start when asked to resume at a message."""
import json, sys, time, os
def out(m): sys.stdout.write((m if isinstance(m,str) else json.dumps(m)) + "\n"); sys.stdout.flush()
mode = os.environ.get("FAKE_MODE")
def log(entry):
    if os.environ.get("FAKE_LOG"):
        with open(os.environ["FAKE_LOG"], "a") as f: f.write(json.dumps(entry) + "\n")
log({"argv": sys.argv[1:]})
if mode == "atcrash" and "--resume-session-at" in sys.argv:
    sys.exit(1)
turns = 0
if mode == "startcrash":
    marker = os.environ["FAKE_MARK"]
    if "--resume" in sys.argv:
        sid = sys.argv[sys.argv.index("--resume")+1]
        if not os.path.exists(marker + sid):
            sys.stderr.write("No conversation found with session ID: %s\n" % sid); sys.exit(1)
    if not os.path.exists(marker + "first"):
        open(marker + "first","w").close(); sys.stderr.write("transient startup failure\n"); sys.exit(1)
init = json.loads(sys.stdin.readline())
out({"type":"control_response","response":{"subtype":"success","request_id":init["request_id"],"response":{}}})
for line in sys.stdin:
    m = json.loads(line)
    if m["type"] != "user": continue
    text = m["message"]["content"]
    log({"prompt": text})
    turns += 1
    out({"type":"assistant","uuid":"a-%d-%s" % (turns, text[:6]),"message":{"content":[]}})
    if text.startswith("fail"):
        out({"type":"result","subtype":"error_max_turns","is_error":True,"result":""}); continue
    if mode == "startcrash":
        sid = sys.argv[sys.argv.index("--session-id")+1] if "--session-id" in sys.argv else sys.argv[sys.argv.index("--resume")+1]
        open(marker + sid, "w").close()
        out({"type":"result","subtype":"success","is_error":False,"result":"ok"}); continue
    if text.startswith("nonobj"):
        out("null")
        out({"type":"result","subtype":"success","is_error":False,"result":"ANSWER TO FIRST"}); continue
    if text.startswith("cancelask"):
        out({"type":"control_request","request_id":"ask-1","request":{"subtype":"can_use_tool","tool_name":"AskUserQuestion",
             "input":{"questions":[{"question":"Q?","header":"h","multiSelect":False,"options":[{"label":"A"},{"label":"B"}]}]}}})
        time.sleep(0.3)
        out({"type":"control_cancel_request","request_id":"ask-1"})
        time.sleep(3)
        out({"type":"result","subtype":"success","is_error":False,"result":"finished work"}); continue
    out({"type":"result","subtype":"success","is_error":False,"result":"answer to: " + text[:20]})
