#!/usr/bin/env python3
"""Bind and run a configured direct Claude invocation without exposing credentials."""
from __future__ import annotations
import argparse, fnmatch, hashlib, json, os, pathlib, shutil, subprocess

OVERRIDES=("ANTHROPIC_API_KEY","ANTHROPIC_AUTH_TOKEN","ANTHROPIC_BASE_URL","CLAUDE_CODE_USE_BEDROCK","CLAUDE_CODE_USE_VERTEX","CLAUDE_CODE_USE_FOUNDRY")
EFFORTS=("native-default","low","medium","high","xhigh","max")

def digest(value: object) -> str:
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def run_json(command:list[str], timeout:int=20)->dict:
 result=subprocess.run(command,capture_output=True,text=True,timeout=timeout,check=True)
 value=json.loads(result.stdout); return value[-1] if isinstance(value,list) else value
def load(args)->dict:
 config_path=pathlib.Path.home()/".agents/second-opinion/config.json"
 cli_path=str(pathlib.Path(shutil.which("claude") or "claude").resolve())
 try: config=json.loads(config_path.read_text())
 except (OSError,json.JSONDecodeError): config={}
 try:
  version=subprocess.run([cli_path,"--version"],capture_output=True,text=True,timeout=10,check=True).stdout.split()[0]
  auth=run_json([cli_path,"auth","status","--json"])
 except (OSError,subprocess.SubprocessError,json.JSONDecodeError,IndexError): version="unavailable"; auth={}
 auth_projection={key:auth.get(key) for key in ("authMethod","apiProvider","subscriptionType")}
 key=f"local/claude/{args.model}/{args.effort}"
 policy=((config.get("directPolicies") or {}).get(key) or {}) if isinstance(config,dict) and config.get("version")==1 else {}
 present=[name for name in OVERRIDES if os.environ.get(name)]
 valid=bool(auth.get("loggedIn") is True and policy.get("metered") is True and policy.get("consent") in ("ask","allow") and policy.get("cliPath")==cli_path and policy.get("cliVersion")==version and policy.get("auth")==auth_projection and isinstance(policy.get("allowedModelUsage"),list) and 1<=len(policy["allowedModelUsage"])<=16 and all(isinstance(x,str) and x.startswith("claude-") and len(x)<=128 for x in policy["allowedModelUsage"]))
 route={"agent":"claude","requestedModel":args.model,"requestedEffort":args.effort,"cliPath":cli_path,"cliVersion":version,"auth":auth_projection,"environmentOverridesPresent":present}
 configured=valid and not present
 projection={"version":1,"route":route,"policy":{"meteredClassification":True if configured else "unknown","consentPolicy":policy.get("consent") if configured else "ask","basis":"configured" if configured else "unavailable","allowedModelUsage":policy.get("allowedModelUsage",[]) if configured else []}}
 projection["routeSha256"]=digest(projection); projection["consentRequired"]=not(configured and policy.get("consent")=="allow")
 return projection

def main()->int:
 parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="action",required=True)
 for action in ("check","run"):
  p=sub.add_parser(action); p.add_argument("--model",required=True); p.add_argument("--effort",choices=EFFORTS,required=True)
  if action=="run":
   p.add_argument("--prompt-file",required=True); p.add_argument("--prompt-sha256",required=True); p.add_argument("--route-sha256",required=True); p.add_argument("--configured-consent",action="store_true"); p.add_argument("--confirmed",action="store_true"); p.add_argument("--timeout",type=int,default=600)
 args=parser.parse_args(); check=load(args)
 if args.action=="check": print(json.dumps(check,separators=(",",":"))); return 0
 if args.configured_consent == args.confirmed: raise SystemExit("choose exactly one consent mode")
 prompt=pathlib.Path(args.prompt_file).read_bytes()
 if len(prompt)>65536: raise SystemExit("prompt exceeds 65536-byte limit")
 if hashlib.sha256(prompt).hexdigest()!=args.prompt_sha256: raise SystemExit("prompt changed since check")
 if check["routeSha256"]!=args.route_sha256: raise SystemExit("direct route changed since check")
 if args.configured_consent:
  if check["consentRequired"]: raise SystemExit("configured consent is not valid for this route")
 elif not args.confirmed: raise SystemExit("refusing route without --configured-consent or --confirmed")
 command=[check["route"]["cliPath"],"-p","--model",args.model,"--tools","Read,Grep,Glob","--permission-mode","plan","--permission-prompts","none","--restricted","--safe-mode","--strict-mcp-config","--mcp-config",'{"mcpServers":{}}',"--no-session-persistence","--output-format","json"]
 if args.effort!="native-default": command += ["--effort",args.effort]
 result=subprocess.run(command,input=prompt,text=False,capture_output=True,timeout=max(1,min(args.timeout,1800)))
 if result.returncode: raise SystemExit("Claude route failed")
 value=json.loads(result.stdout); records=value if isinstance(value,list) else [value]; final=next((x for x in reversed(records) if isinstance(x,dict) and isinstance(x.get("result"),str)),{})
 models=sorted((final.get("modelUsage") or {}).keys()); allowed=check["policy"]["allowedModelUsage"]
 model_usage_allowed=None if args.confirmed else bool(models) and all(any(fnmatch.fnmatchcase(model,pattern) for pattern in allowed) for model in models)
 status="ok" if final and not final.get("is_error") and (args.confirmed or model_usage_allowed) else "model-mismatch" if final and not final.get("is_error") else "failed"
 output={"version":1,"status":status,"route":check["route"],"policy":check["policy"],"routeSha256":check["routeSha256"],"modelUsage":models,"modelUsageAllowed":model_usage_allowed,"response":final.get("result","")[:65536]}
 print(json.dumps(output,separators=(",",":"))); return 0 if output["status"]=="ok" else 1
if __name__=="__main__": raise SystemExit(main())
