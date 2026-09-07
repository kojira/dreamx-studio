import unittest
from dreamx.auth import Sessions, Unauthorized, RateLimited, check_origin

class AuthTests(unittest.TestCase):
    def test_secret_length(self):
        with self.assertRaises(ValueError): Sessions('short')

    def test_expiry_csrf_logout(self):
        now=[0]; auth=Sessions('x'*32,clock=lambda:now[0])
        s=auth.login('x'*32)
        self.assertEqual(auth.require(s.token),s)
        with self.assertRaises(Unauthorized): auth.require(s.token,modifying=True)
        auth.require(s.token,s.csrf,modifying=True)
        now[0]=8*3600
        with self.assertRaises(Unauthorized): auth.require(s.token)
        s=auth.login('x'*32); auth.logout(s.token)
        with self.assertRaises(Unauthorized): auth.require(s.token)

    def test_rate_limit_and_restart(self):
        now=[0]; auth=Sessions('x'*32,clock=lambda:now[0])
        for _ in range(5):
            with self.assertRaises(Unauthorized): auth.login('bad')
        with self.assertRaises(RateLimited): auth.login('x'*32)
        now[0]=60; s=auth.login('x'*32)
        with self.assertRaises(Unauthorized): Sessions('x'*32).require(s.token)

    def test_origin(self):
        check_origin('127.0.0.1:8780',None,modifying=False)
        check_origin('127.0.0.1:8780','http://127.0.0.1:8780',modifying=True)
        for host,origin in [('evil.test',None),('127.0.0.1:8780','http://evil.test'),('127.0.0.1:8780',None)]:
            with self.assertRaises(Unauthorized): check_origin(host,origin,modifying=True)
