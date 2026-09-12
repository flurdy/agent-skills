import hashlib, json, os, pathlib, subprocess, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
HELPER=ROOT/'scripts/direct-route.py'

class DirectRouteTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.temp.name); (self.root/'bin').mkdir(); self.bin=self.root/'bin/claude'; self.log=self.root/'log'
  self.bin.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "2.1.267 (Claude Code)"; exit; fi\nif [ "$1" = "auth" ]; then echo \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"max","email":"private"}\'; exit; fi\nprintf "%s\\n" "$*" > "$DIRECT_LOG"\ncat >/dev/null\nprintf \'%s\\n\' \'{"type":"result","is_error":false,"result":"review","modelUsage":{"claude-opus-5":{},"claude-haiku-4-5-20251001":{}}}\'\n'); self.bin.chmod(0o700)
  self.config=self.root/'.agents/second-opinion/config.json'; self.config.parent.mkdir(parents=True); self.prompt=self.root/'prompt'; self.prompt.write_text('safe prompt')
  self.policy={"version":1,"profiles":{},"directPolicies":{"local/claude/opus/native-default":{"metered":True,"consent":"allow","cliPath":str(self.bin.resolve()),"cliVersion":"2.1.267","auth":{"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"max"},"allowedModelUsage":["claude-opus-*","claude-haiku-*"]}}}; self.config.write_text(json.dumps(self.policy))
  self.env={**os.environ,"HOME":str(self.root),"PATH":str(self.root/'bin')+os.pathsep+os.environ['PATH'],"DIRECT_LOG":str(self.log)}
  for key in ('ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY'): self.env.pop(key,None)
 def tearDown(self): self.temp.cleanup()
 def run_helper(self,*args,check=True): return subprocess.run(['python3',str(HELPER),*args],env=self.env,text=True,capture_output=True,check=check,timeout=10)
 def test_policy_and_command_sources_cannot_be_selected_by_the_caller(self):
  self.assertNotEqual(self.run_helper('check','--model','opus','--effort','native-default','--config',str(self.root/'other'),check=False).returncode,0)
  self.assertNotEqual(self.run_helper('check','--model','opus','--effort','native-default','--claude-command',str(self.bin),check=False).returncode,0)
 def test_check_binds_invocation_without_exposing_account_data(self):
  value=json.loads(self.run_helper('check','--model','opus','--effort','native-default').stdout)
  self.assertFalse(value['consentRequired']); self.assertEqual(value['policy']['basis'],'configured'); self.assertNotIn('email',json.dumps(value)); self.assertEqual(len(value['routeSha256']),64); self.assertFalse(self.log.exists())
 def test_missing_mismatch_or_environment_override_requires_confirmation(self):
  self.assertTrue(json.loads(self.run_helper('check','--model','fable','--effort','native-default').stdout)['consentRequired'])
  self.policy['directPolicies']['local/claude/opus/native-default']['cliVersion']='old'; self.config.write_text(json.dumps(self.policy)); self.assertTrue(json.loads(self.run_helper('check','--model','opus','--effort','native-default').stdout)['consentRequired'])
  self.policy['version']=2; self.config.write_text(json.dumps(self.policy)); self.assertTrue(json.loads(self.run_helper('check','--model','opus','--effort','native-default').stdout)['consentRequired'])
  self.policy['version']=1; self.policy['directPolicies']['local/claude/opus/native-default']['cliVersion']='2.1.267'; self.policy['directPolicies']['local/claude/opus/native-default']['allowedModelUsage']=['*']; self.config.write_text(json.dumps(self.policy)); self.assertTrue(json.loads(self.run_helper('check','--model','opus','--effort','native-default').stdout)['consentRequired'])
  env={**self.env,'ANTHROPIC_API_KEY':'redacted'}; result=subprocess.run(['python3',str(HELPER),'check','--model','opus','--effort','native-default'],env=env,text=True,capture_output=True,check=True); self.assertTrue(json.loads(result.stdout)['consentRequired']); self.assertNotIn('redacted',result.stdout)
 def test_run_rechecks_digest_uses_stdin_and_reports_actual_models(self):
  check=json.loads(self.run_helper('check','--model','opus','--effort','native-default').stdout)
  result=json.loads(self.run_helper('run','--model','opus','--effort','native-default','--prompt-file',str(self.prompt),'--route-sha256',check['routeSha256'],'--prompt-sha256',hashlib.sha256(self.prompt.read_bytes()).hexdigest(),'--configured-consent').stdout)
  self.assertEqual(result['response'],'review'); self.assertEqual(result['modelUsage'],['claude-haiku-4-5-20251001','claude-opus-5']); self.assertTrue(result['modelUsageAllowed']); self.assertIn('--model opus',self.log.read_text()); self.assertNotIn('safe prompt',self.log.read_text())
 def test_unexpected_actual_models_fail_the_run_after_preserving_evidence(self):
  self.policy['directPolicies']['local/claude/opus/native-default']['allowedModelUsage']=['claude-opus-*']; self.config.write_text(json.dumps(self.policy)); check=json.loads(self.run_helper('check','--model','opus','--effort','native-default').stdout)
  result=self.run_helper('run','--model','opus','--effort','native-default','--prompt-file',str(self.prompt),'--route-sha256',check['routeSha256'],'--prompt-sha256',hashlib.sha256(self.prompt.read_bytes()).hexdigest(),'--configured-consent',check=False)
  self.assertNotEqual(result.returncode,0); self.assertEqual(json.loads(result.stdout)['status'],'model-mismatch')
 def test_confirmed_unknown_route_runs_but_does_not_persist_approval(self):
  check=json.loads(self.run_helper('check','--model','fable','--effort','native-default').stdout)
  result=json.loads(self.run_helper('run','--model','fable','--effort','native-default','--prompt-file',str(self.prompt),'--route-sha256',check['routeSha256'],'--prompt-sha256',hashlib.sha256(self.prompt.read_bytes()).hexdigest(),'--confirmed').stdout)
  self.assertEqual(result['policy']['basis'],'unavailable'); self.assertIsNone(result['modelUsageAllowed'])
  self.assertTrue(json.loads(self.run_helper('check','--model','fable','--effort','native-default').stdout)['consentRequired'])
 def test_run_rejects_stale_or_unconfirmed_policy_before_launch(self):
  check=json.loads(self.run_helper('check','--model','opus','--effort','native-default').stdout)
  for extra in ([],['--route-sha256','0'*64,'--configured-consent']):
   result=self.run_helper('run','--model','opus','--effort','native-default','--prompt-file',str(self.prompt),'--route-sha256',check['routeSha256'],'--prompt-sha256',hashlib.sha256(self.prompt.read_bytes()).hexdigest(),*extra,check=False)
   self.assertNotEqual(result.returncode,0); self.assertFalse(self.log.exists())
  both=self.run_helper('run','--model','opus','--effort','native-default','--prompt-file',str(self.prompt),'--route-sha256',check['routeSha256'],'--prompt-sha256',hashlib.sha256(self.prompt.read_bytes()).hexdigest(),'--configured-consent','--confirmed',check=False)
  self.assertNotEqual(both.returncode,0)
  self.prompt.write_bytes(b'x'*65537); large=self.run_helper('run','--model','opus','--effort','native-default','--prompt-file',str(self.prompt),'--route-sha256',check['routeSha256'],'--prompt-sha256',hashlib.sha256(self.prompt.read_bytes()).hexdigest(),'--configured-consent',check=False); self.assertNotEqual(large.returncode,0)

if __name__=='__main__': unittest.main()
