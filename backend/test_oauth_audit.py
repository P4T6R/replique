import asyncio, json, time, unittest
from unittest.mock import AsyncMock
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from fastapi import HTTPException
from backend.oauth import OAuth, Pending, ISSUER

class AuditIdentityTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.service=OAuth()
  self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  self.jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
  self.jwk.update(kid='audit', use='sig')
  self.service.metadata=AsyncMock(return_value={'jwks_uri':ISSUER+'/jwks'})
  self.service.json_request=AsyncMock(return_value={'keys':[self.jwk]})
  self.pending=Pending('s','nonce','v','http://127.0.0.1:8000/api/auth/callback','browser','oaiapp_audit',None)
  self.claims={'sub':'audit-sub','iss':ISSUER,'aud':'oaiapp_audit','nonce':'nonce','iat':time.time()-1,'exp':time.time()+300}
 async def validate(self, claims, key=None):
  token=jwt.encode(claims,key or self.key,algorithm='RS256',headers={'kid':'audit'})
  return await self.service.validate_identity(token,self.pending,'oaiapp_audit')
 async def test_valid(self):
  self.assertEqual((await self.validate(self.claims))['sub'],'audit-sub')
 async def test_invalid_claims(self):
  for field,value in [('sub',''),('iss','https://evil.example'),('aud','other'),('nonce','wrong'),('exp',time.time()-10),('iat',time.time()+500)]:
   with self.subTest(field=field),self.assertRaises(HTTPException):
    await self.validate({**self.claims,field:value})
 async def test_missing_claims(self):
  for field in self.claims:
   claims={k:v for k,v in self.claims.items() if k!=field}
   with self.subTest(field=field),self.assertRaises(HTTPException): await self.validate(claims)
 async def test_foreign_signer(self):
  key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  with self.assertRaises(HTTPException): await self.validate(self.claims,key)
 async def test_reauth_identity_mismatch(self):
  self.pending.subject='another-user'
  with self.assertRaises(HTTPException): await self.validate(self.claims)
 async def test_multiple_audiences_need_azp(self):
  with self.assertRaises(HTTPException): await self.validate({**self.claims,'aud':['oaiapp_audit','other']})
 async def test_duplicate_signing_key(self):
  self.service.json_request=AsyncMock(return_value={'keys':[self.jwk,self.jwk]})
  with self.assertRaises(HTTPException): await self.validate(self.claims)

 async def test_single_audience_wrong_authorized_party(self):
  with self.assertRaises(HTTPException): await self.validate({**self.claims,'azp':'other'})
 async def test_jwks_malformed_entries(self):
  for keys in [[None], ['wrong'], None, {}]:
   self.service.json_request=AsyncMock(return_value={'keys':keys})
   with self.subTest(keys=keys),self.assertRaises(HTTPException): await self.validate(self.claims)


class AuditStreamBounds(unittest.IsolatedAsyncioTestCase):
 async def test_unterminated_event_bounded_before_line(self):
  import httpx
  from backend.chatgpt_provider import bounded_lines, MAX_STREAM
  response=httpx.Response(200,content=b'x'*(MAX_STREAM+1))
  with self.assertRaises(HTTPException):
   async for _ in bounded_lines(response): self.fail('Oversized line escaped the bound')
 async def test_utf8_split_across_chunks(self):
  import httpx
  from backend.chatgpt_provider import bounded_lines
  class Parts(httpx.AsyncByteStream):
   async def __aiter__(self):
    for chunk in [b'data: "caf\xc3',b'\xa9"\r',b'\n\n']: yield chunk
  response=httpx.Response(200,stream=Parts())
  self.assertEqual([line async for line in bounded_lines(response)],['data: "café"',''])
 async def test_invalid_utf8_rejected(self):
  import httpx
  from backend.chatgpt_provider import bounded_lines
  with self.assertRaises(UnicodeDecodeError):
   [line async for line in bounded_lines(httpx.Response(200,content=b'\xff\n'))]

class AuditCallbackExchange(unittest.TestCase):
 def test_successful_exchange_uses_issued_client_and_exact_pkce_binding(self):
  import os, tempfile, hashlib, base64
  from unittest.mock import patch
  from urllib.parse import urlsplit, parse_qs
  from fastapi.testclient import TestClient
  from backend.app import app
  service=OAuth()
  origin='http://127.0.0.1:8000'
  tokens={'access_token':'audit-access','refresh_token':'audit-refresh','id_token':'audit-id',
          'token_type':'Bearer','expires_in':300,'scope':'openid resource.invoke chatgpt.tokens.use.direct'}
  with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'REPLIQUE_OAUTH_ENABLED':'1','REPLIQUE_DATA_DIR':directory}), patch('backend.oauth.oauth',service), TestClient(app,base_url=origin) as browser:
   response=browser.post('/api/auth/login',headers={'Origin':origin,'X-Replique-Request':'1'})
   self.assertEqual(response.status_code,200)
   self.assertIn('HttpOnly',response.headers['set-cookie'])
   self.assertIn('SameSite=lax',response.headers['set-cookie'])
   params=parse_qs(urlsplit(response.json()['authorization_url']).query)
   pending=service.pending
   expected_challenge=base64.urlsafe_b64encode(hashlib.sha256(pending.verifier.encode()).digest()).decode().rstrip('=')
   self.assertEqual(params['code_challenge'],[expected_challenge])
   with patch.object(service,'json_request',new_callable=AsyncMock,return_value=tokens) as exchange, patch.object(service,'validate_identity',new_callable=AsyncMock,return_value={'sub':'audit-sub','email':'audit@example.invalid'}):
    callback=browser.get('/api/auth/callback',params={'state':pending.state,'code':'audit-code','client_id':'oaiapp_issued'},follow_redirects=False)
   self.assertEqual(callback.status_code,303)
   sent=exchange.call_args.kwargs['data']
   self.assertEqual(sent['client_id'],'oaiapp_issued')
   self.assertEqual(sent['redirect_uri'],params['redirect_uri'][0])
   self.assertEqual(sent['code_verifier'],pending.verifier)
   self.assertEqual(sent['resource'],'https://api.openai.com/v1')
   self.assertIsNone(service.pending)
   self.assertEqual(service.session.client_id,'oaiapp_issued')
   status=browser.get('/api/auth/status')
   self.assertNotIn('audit-access',status.text)
   self.assertNotIn('audit-refresh',status.text)
   self.assertNotIn('audit-id',status.text)
   self.assertEqual(browser.get('/api/auth/callback',params={'state':pending.state,'code':'audit-code','client_id':'oaiapp_issued'}).status_code,400)

class AuditLogoutRace(unittest.IsolatedAsyncioTestCase):
 async def test_logout_after_refresh_cancels_generation_without_resurrection(self):
  import os, httpx
  from unittest.mock import patch
  from starlette.requests import Request
  from backend.oauth import Session, logout
  service=OAuth()
  service.session=Session('browser','issued','sub',None,'old','r1',{'openid','resource.invoke','chatgpt.tokens.use.direct'},0)
  started, release=asyncio.Event(),asyncio.Event()
  async def refresh(*args, **kwargs):
   started.set()
   await release.wait()
   return {'access_token':'new','refresh_token':'r2','token_type':'Bearer','expires_in':300}
  service.json_request=AsyncMock(side_effect=refresh)
  service.metadata=AsyncMock(side_effect=httpx.ConnectError('mock offline'))
  async def generation():
   task=asyncio.current_task()
   service.generations.add(task)
   try:
    await service.access('browser')
    await asyncio.Event().wait()
   finally: service.generations.discard(task)
  scope={'type':'http','method':'POST','path':'/api/auth/logout','scheme':'http','server':('127.0.0.1',8000),'query_string':b'',
         'headers':[(b'host',b'127.0.0.1:8000'),(b'origin',b'http://127.0.0.1:8000'),(b'x-replique-request',b'1'),(b'cookie',b'replique_session=browser')]}
  with patch.dict(os.environ,{'REPLIQUE_OAUTH_ENABLED':'1'}),patch('backend.oauth.oauth',service):
   task=asyncio.create_task(generation())
   await started.wait()
   ending=asyncio.create_task(logout(Request(scope)))
   await asyncio.sleep(0)
   release.set()
   result=await ending
   with self.assertRaises(asyncio.CancelledError): await task
  self.assertIsNone(service.session)
  self.assertFalse(service.generations)
  self.assertEqual(result.status_code,200)
