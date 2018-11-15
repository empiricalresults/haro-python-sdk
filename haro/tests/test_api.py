import json
import time
from unittest import TestCase

import requests_mock

from haro import api


class TestEvent(TestCase):
    def test_validate(self):
        now = int(time.time() * 1000)
        # Valid event
        e = api.Event(id="event-id-1", action="action_1", item="item-1", timestamp=now,
                      user="u1", context={"k1": "v1", "K-e-y-2": 3.1415})
        e.validate()
        # dot is valid
        e = api.Event(id="event.id.1", action="action_1", item="item-1", timestamp=now,
                      user="u1", context={"k.1": "v1", "K-e-y-2": 3.1415})
        e.validate()
        # Non alphanumeric action
        e = api.Event(id="event-id-1", action="a1?", item="i1", timestamp=now, user="u1",
                      context={"k1": "v1"})
        with self.assertRaises(ValueError):
            e.validate()
        # Long item
        e = api.Event(id="event-id-1", action="a1", item="long-str" * 100,
                      timestamp=now, user="u1", context={"k1": "v1"})
        with self.assertRaises(ValueError):
            e.validate()
        # Missing timestamp
        with self.assertRaises(ValueError):
            api.Event(id="event-id-1", action="action_1", item="item-1", timestamp=None,
                          user="u1", context={"k1": "v1"})
        # Invalid timestamp
        e = api.Event(id="event-id-1", action="action_1", item="item-1", timestamp=10**100,
                      user="u1", context={"k1": "v1"})
        with self.assertRaises(ValueError):
            e.validate()

        # Invalid context
        e = api.Event(id="event-id-1", action="action_1", item="item-1", timestamp=now,
                      user="u1", context="I am not a dictionary")
        with self.assertRaises(ValueError):
            e.validate()

        # Bad context key
        e = api.Event(id="event-id-1", action="action_1", item="item-1", timestamp=now,
                      user="u1", context={"k1#$%": "v1"})
        with self.assertRaises(ValueError):
            e.validate()
        # nested context value
        e = api.Event(id="event-id-1", action="action_1", item="item-1", timestamp=now,
                      user="u1", context={"k2": {"k3": [1, 2]}})
        with self.assertRaises(ValueError):
            e.validate()


class TestHaroAPIClient(TestCase):
    def setUp(self):
        api._EVENTS_API_ENDPOINT = "http://test-events-api/"
        api._EVENTS_API_VERSION = "v31.415"
        api._PREDICTION_API_ENDPOINT = "http://test-prediction-api/"
        api._PREDICTION_API_VERSION = "v42.526"

    @requests_mock.mock()
    def test_send_events(self, m):
        m.post('http://test-events-api/v31.415/events', text=json.dumps({'status': 'ok', 'count': 2}))
        now = int(time.time() * 1000)
        e1 = api.Event(id="event-id-1", action="action_1", item="item-1", timestamp=now,
                       user="u1", context={"k1": "v1", "k2": 3.1415})
        e2 = api.Event(id="event-id-2", action="action-2", item="item-2", timestamp=now,
                       user="u1", context={})
        haro_api = api.HaroAPIClient(api_id="test-api-id", api_key="test-api-key")
        num_sent, errors = haro_api.send_events([e1, e2])
        self.assertEqual(num_sent, 2)
        self.assertEqual(errors, [])
        self.assertEqual(m.last_request.json(),
                         [{'action': 'action_1', 'user': 'u1',
                           'context': {'k1': 'v1', 'k2': 3.1415},
                           'item': 'item-1', 'id': 'event-id-1', 'ts': now},
                          {'action': 'action-2', 'user': 'u1', 'context': {},
                           'item': 'item-2', 'id': 'event-id-2', 'ts': now}])

    @requests_mock.mock()
    def test_rank(self, m):
        m.get('http://test-prediction-api/v42.526/rank/rank-items-for-action-watch/user/u1/',
              text=json.dumps({'entities': ['item-3', 'item-1', 'item-2'], 'scores': [0.79, 0.43, 0.05]}),
              headers={'X-ADDITIONAL-INFO': 'some-value', 'other-headers': 'present'})
        haro_api = api.HaroAPIClient(api_id="test-api-id", api_key="test-api-key")
        r = haro_api.rank(pid="rank-items-for-action-watch", user="u1", subset=['item-1', 'item-2', 'item-3'],
                          include_scores=True)
        self.assertEqual(r.entities, ['item-3', 'item-1', 'item-2'])
        self.assertEqual(r.scores, [0.79, 0.43, 0.05])
        self.assertEqual(r.meta, {"ADDITIONAL-INFO": "some-value"})

    @requests_mock.mock()
    def test_predict(self, m):
        m.get('http://test-prediction-api/v42.526/predict/predict-avg-context-for-action-watch-context-duration_seconds/user/u1/',
              text=json.dumps({'value': 31.41}),
              headers={'X-ADDITIONAL-INFO': 'some-value', 'other-headers': 'present'})
        haro_api = api.HaroAPIClient(api_id="test-api-id", api_key="test-api-key")
        r = haro_api.predict(pid="predict-avg-context-for-action-watch-context-duration_seconds", user="u1")
        self.assertEqual(r.value, 31.41)
        self.assertEqual(r.meta, {"ADDITIONAL-INFO": "some-value"})

    @requests_mock.mock()
    def test_anticipate(self, m):
        m.get('http://test-prediction-api/v42.526/anticipate/anticipate-condition-eebc14df57-within-3-hours/user/u1/',
              text=json.dumps({'value': 0.79}),
              headers={'X-ADDITIONAL-INFO': 'some-value', 'other-headers': 'present'})
        haro_api = api.HaroAPIClient(api_id="test-api-id", api_key="test-api-key")
        r = haro_api.anticipate(pid="anticipate-condition-eebc14df57-within-3-hours", user="u1", name="v2")
        self.assertEqual(r.value, 0.79)
        self.assertEqual(r.meta, {"ADDITIONAL-INFO": "some-value"})

    @requests_mock.mock()
    def test_custom(self, m):
        m.get('http://test-prediction-api/v42.526/custom/custom-predictor-for-home-page/user/u1/',
              text=json.dumps({'value': {"custom-values": [3, 1, 4]}}),
              headers={'X-ADDITIONAL-INFO': 'some-value', 'other-headers': 'present'})
        haro_api = api.HaroAPIClient(api_id="test-api-id", api_key="test-api-key")
        r = haro_api.custom(pid="custom-predictor-for-home-page", user="u1", name="v2")
        self.assertEqual(r.value, {"custom-values": [3, 1, 4]})
        self.assertEqual(r.meta, {"ADDITIONAL-INFO": "some-value"})

    @requests_mock.mock()
    def test_all_predictions(self, m):
        api_result = [
            {
                "pid": "rank-items-for-action-watch",
                "name": "rank-watch",
                "predictions": {
                    'entities': ['item-3', 'item-1', 'item-2'], 'scores': [0.79, 0.43, 0.05]
                },
            },
            {
                "pid": "predict-avg-context-for-action-watch-context-duration_seconds",
                "name": "avg-duration",
                "predictions": {
                    'value': 31.41
                },
            },
            {
                "pid": "anticipate-condition-eebc14df57-within-3-hours",
                "name": "anticipate-watch",
                "predictions": {
                    'value': 0.79
                },
            },
        ]
        m.get('http://test-prediction-api/v42.526/all-predictions/user/u1/', text=json.dumps(api_result))
        haro_api = api.HaroAPIClient(api_id="test-api-id", api_key="test-api-key")
        results = haro_api.all_predictions(user="u1")
        self.assertEquals(len(results), 3)
        r1, r2, r3 = results
        self.assertEquals(r1.pid, "rank-items-for-action-watch")
        self.assertEquals(r1.name, "rank-watch")
        self.assertEquals(r1.entities, ['item-3', 'item-1', 'item-2'])
        self.assertEqual(r1.scores, [0.79, 0.43, 0.05])
        self.assertEquals(r2.pid, "predict-avg-context-for-action-watch-context-duration_seconds")
        self.assertEquals(r2.name, "avg-duration")
        self.assertEquals(r2.value, 31.41)
        self.assertEquals(r3.pid, "anticipate-condition-eebc14df57-within-3-hours")
        self.assertEquals(r3.name, "anticipate-watch")
        self.assertEquals(r3.value, 0.79)
