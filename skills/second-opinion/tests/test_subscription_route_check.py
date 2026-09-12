import json, os, pathlib, subprocess, tempfile, unittest
HELPER=pathlib.Path(__file__).resolve().parents[1]/'scripts/subscription-route-check.py'
class SubscriptionCheckTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); root=pathlib.Path(self.temp.name); (root/'bin').mkdir(); self.env={**os.environ,'PATH':str(root/'bin')+os.pathsep+os.environ['PATH']}
  (root/'bin/claude').write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"max","email":"private"}\'\n'); (root/'bin/claude').chmod(0o700)
  (root/'bin/codex').write_text('#!/bin/sh\necho "Logged in using ChatGPT" >&2\n'); (root/'bin/codex').chmod(0o700)
  for key in ('ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY','OPENAI_API_KEY','OPENAI_BASE_URL','CODEX_API_KEY','CODEX_ACCESS_TOKEN'): self.env.pop(key,None)
 def tearDown(self): self.temp.cleanup()
 def check(self,route,env=None): return json.loads(subprocess.run(['python3',str(HELPER),route],env=env or self.env,text=True,capture_output=True,check=True,timeout=10).stdout)
 def test_reports_stable_subscription_classification_without_account_or_version(self):
  self.assertEqual(self.check('claude'),{'version':1,'route':'claude','subscriptionLogin':True,'auth':'claude.ai','apiOverridesPresent':[]})
  self.assertEqual(self.check('codex'),{'version':1,'route':'codex','subscriptionLogin':True,'auth':'ChatGPT','apiOverridesPresent':[]})
 def test_reports_override_names_without_values(self):
  value=self.check('claude',{**self.env,'ANTHROPIC_API_KEY':'secret'}); self.assertFalse(value['subscriptionLogin']); self.assertEqual(value['apiOverridesPresent'],['ANTHROPIC_API_KEY']); self.assertNotIn('secret',json.dumps(value))
 def test_rejects_unknown_route(self):
  result=subprocess.run(['python3',str(HELPER),'gemini'],env=self.env,text=True,capture_output=True); self.assertNotEqual(result.returncode,0)
if __name__=='__main__': unittest.main()
