import unittest
from unittest.mock import MagicMock, patch

from scripts.flows_accounts import Conflict, execute, inspect, normalize


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.factory = MagicMock(return_value=self.connection)
        self.payload = {'batches': [{'account_id': '100', 'record_ids': ['1', '2']}]}
        self.records = {'1': {'account': None, 'version': '40'},
                        '2': {'account': None, 'version': '41'}}

    def execute(self, operation, payload, actor='operador', repository='owner/repo'):
        return execute(operation, payload, 's' * 48, repository, actor, self.factory)

    def verify(self):
        with patch('scripts.flows_accounts.inspect', return_value=({100: 'Gastos'}, self.records)):
            return self.execute('verify', self.payload)['verification_token']

    def save(self, token):
        with patch('scripts.flows_accounts.inspect', return_value=({100: 'Gastos'}, self.records)):
            return self.execute('save', {'verification_token': token})

    def test_duplicate_records_rejected(self):
        with self.assertRaises(ValueError):
            normalize({'batches': self.payload['batches'] * 2})

    def test_invalid_identifiers_rejected(self):
        for value in (True, -1, '1; DROP TABLE x', 1.5, None):
            with self.assertRaises(ValueError):
                normalize({'batches': [{'account_id': value, 'record_ids': [1]}]})

    def test_limit_and_empty_batches(self):
        for ids in ([], list(range(1, 1002))):
            with self.assertRaises(ValueError):
                normalize({'batches': [{'account_id': 100, 'record_ids': ids}]})

    def test_verify_never_updates(self):
        self.verify()
        self.assertFalse(any('UPDATE' in str(call) for call in self.cursor.execute.call_args_list))
        self.connection.close.assert_called_once()

    def test_already_assigned_rejected(self):
        self.records['1']['account'] = 200
        with self.assertRaises(Conflict):
            self.verify()

    def test_save_after_verification(self):
        token = self.verify()
        self.cursor.fetchall.return_value = [(1,), (2,)]
        result = self.save(token)
        self.assertTrue(result['saved'])
        self.assertEqual(result['count'], 2)
        self.assertIn('UPDATE', self.cursor.execute.call_args.args[0])
        self.assertEqual(self.cursor.execute.call_args.args[1], (100, [1, 2]))
        self.connection.__exit__.assert_called_with(None, None, None)

    def test_concurrent_change_rejects_entire_save(self):
        token = self.verify()
        self.records['2']['version'] = '42'
        self.cursor.reset_mock()
        with self.assertRaises(Conflict):
            self.save(token)
        self.assertFalse(any('UPDATE' in str(call) for call in self.cursor.execute.call_args_list))
        self.assertIsNotNone(self.connection.__exit__.call_args.args[0])

    def test_partial_update_rolls_back(self):
        token = self.verify()
        self.cursor.fetchall.return_value = [(1,)]
        with self.assertRaises(Conflict):
            self.save(token)
        self.assertIsNotNone(self.connection.__exit__.call_args.args[0])

    def test_second_batch_failure_rolls_back_all(self):
        self.payload['batches'] = [{'account_id': 100, 'record_ids': [1]},
                                   {'account_id': 100, 'record_ids': [2]}]
        token = self.verify()
        self.cursor.fetchall.side_effect = [[(1,)], []]
        with self.assertRaises(Conflict):
            self.save(token)
        self.assertIsNotNone(self.connection.__exit__.call_args.args[0])

    def test_commit_failure_never_returns_success(self):
        token = self.verify()
        self.cursor.fetchall.return_value = [(1,), (2,)]
        self.connection.__exit__.side_effect = RuntimeError('commit failed')
        with self.assertRaises(RuntimeError):
            self.save(token)
        self.assertEqual(self.connection.close.call_count, 2)

    def test_retry_confirms_without_writing_again(self):
        token = self.verify()
        for row in self.records.values():
            row['account'] = 100
        self.cursor.reset_mock()
        self.assertTrue(self.save(token)['already_saved'])
        self.assertFalse(any('UPDATE' in str(call) for call in self.cursor.execute.call_args_list))

    def test_expired_or_tampered_verification(self):
        token = self.verify()
        with self.assertRaises(Conflict):
            self.save(token + 'x')
        with patch('time.time', return_value=9999999999), self.assertRaises(Conflict):
            self.save(token)

    def test_receipt_bound_to_actor_and_repository(self):
        token = self.verify()
        self.factory.reset_mock()
        for kwargs in ({'actor': 'otro'}, {'repository': 'otro/repo'}):
            with self.assertRaises(Conflict):
                self.execute('save', {'verification_token': token}, **kwargs)
        self.factory.assert_not_called()

    def test_catalog_and_missing_records_checked(self):
        batches = normalize(self.payload)
        self.cursor.fetchall.return_value = []
        with self.assertRaises(Conflict):
            inspect(self.cursor, batches)
        self.cursor.fetchall.side_effect = [[(100, 'Gastos')], [(1, None, '40')]]
        with self.assertRaises(Conflict):
            inspect(self.cursor, batches, lock=True)
        query, parameters = self.cursor.execute.call_args.args
        self.assertIn('FOR UPDATE', query)
        self.assertIn('flowid = ANY(%s)', query)
        self.assertEqual(parameters[0], [1, 2])


if __name__ == '__main__':
    unittest.main()
