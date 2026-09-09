import unittest
from evaluation_receipt import seeded_login_observations


class PreparationReceipt(unittest.TestCase):
    def test_only_completed_seed_authentication_assertion_is_evidence(self):
        events=[
            dict(sequence=1,stage='target_discovery',intent='toBeVisible',outcome='completed',prerequisites=['ログイン ippan']),
            dict(sequence=2,stage='operation',intent='ログインフォーム送信',outcome='completed',prerequisites=['ログイン ippan']),
            dict(sequence=3,stage='business_assertion',intent='toBeVisible',outcome='failed',prerequisites=['ログイン ippan']),
            dict(sequence=4,stage='business_assertion',intent='toBeVisible',outcome='completed',prerequisites=['ログイン yamada']),
        ]
        self.assertEqual(seeded_login_observations(events),[])
        events.append(dict(sequence=5,stage='business_assertion',intent='toBeVisible',outcome='completed',prerequisites=['UI前提','ログイン kacho']))
        self.assertEqual(seeded_login_observations(events),[{'sequence':5,'account':'kacho'}])


if __name__=='__main__':unittest.main()
