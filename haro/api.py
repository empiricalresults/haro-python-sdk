import json
import re

import posixpath

import datetime
import requests
from requests import HTTPError
from urllib3.exceptions import RequestError
from six import string_types

ALPHA_NUMERIC_REGEX = "^[\.a-zA-Z0-9_-]{1,128}$"

_EVENTS_API_ENDPOINT = "https://events.haro.io"
_EVENTS_API_VERSION = "v16.10"
_PREDICTION_API_ENDPOINT = "https://api.haro.io"
_PREDICTION_API_VERSION = "v17.12"

_MAX_RETRIES = 3


class Event(object):
    """
    Represents a single user interaction with an app,
    For instance, user watched a video, user played a mission, or user booked an appointment.
    """

    # noinspection PyShadowingBuiltins
    def __init__(self, id, action, item, timestamp, user, context=None):
        """
        Args:
            id (str): unique event id. used for de-duplication
            user (str): user id
            action (str): action that determines the type of interaction
            item (str): the item that the user interacted with
            timestamp (int): timestamp, milliseconds since unix epoch
            context (dict or None): additional key-value properties of the interaction
        """
        self.id = id
        self.action = action
        self.item = item
        self.user = user
        self.context = context or {}
        try:
            self.timestamp = int(timestamp)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("timestamp must be an int, got: {}".format(timestamp))

    def as_dict(self):
        return dict(id=self.id, action=self.action, item=self.item,
                    ts=self.timestamp, user=self.user, context=self.context)

    def validate(self):
        """
        Checks that this is a valid Haro event
        Raises:
            ValueError: in case the event is not valid
        """
        for required_alphanumeric in ('id', 'action', 'item', 'user'):
            value = getattr(self, required_alphanumeric, None)
            if value is None:
                raise ValueError("{} is required".format(required_alphanumeric))
            try:
                match = re.match(ALPHA_NUMERIC_REGEX, value)
            except TypeError:
                match = False
            if not match:
                raise ValueError("{} is an invalid value for {}".format(value, required_alphanumeric))
        try:
            _ = datetime.datetime.fromtimestamp(self.timestamp / 1000.0)
        except (OverflowError, ValueError):
            raise ValueError("timestamp is not valid: {}".format(self.timestamp))
        if not isinstance(self.context, dict):
            raise ValueError("Event context must be a dictionary. Got: {}".format(self.context))
        for (k, v) in self.context.items():
            if not re.match(ALPHA_NUMERIC_REGEX, k):
                raise ValueError("{} is an invalid context key".format(k))
            if not isinstance(v, (int, float)) and not isinstance(v, string_types):
                raise ValueError("context values must either be numeric or string. Got: ".format(v))


class HaroAPIClient(object):
    def __init__(self, api_id, api_key):
        """
        Haro API Client.
        A thin wrapper for making calls to Haro events and prediction REST API

        Args:
            api_id (str): Application API id
            api_key (str): Application API key
        Notes:
            A client is initialized for a single app and can only send events to and ask for prediction for
            that application.
        """
        self.api_id = api_id
        self.api_key = api_key

    def send_events(self, events, validate=True):
        """
        Args:
            events (list of Event): list of Event objects to send to Haro
            validate (bool): when True, do validation before sending the events
                When false, the server will accept all valid events and ignore invalid events
        Returns:
           (int, list): number of events successfully delivered, and a list of errors
        Raises:
            IOError: in case of http issues
            ValueError: in case of invalid events
        """
        if validate:
            for e in events:
                e.validate()
        return self._send_events_with_retry(events, validate=validate, num_retries=_MAX_RETRIES)

    def _send_events_with_retry(self, events, validate, num_retries):
        """
        Args:
            events (list of Event):
        Returns:
            (int, list): number of events successfully delivered, and a list of errors
        """

        headers = self._build_request_headers()
        url = posixpath.join(_EVENTS_API_ENDPOINT, _EVENTS_API_VERSION, "events")
        params = {}
        if not validate:
            params['ignore_invalid'] = True
        data = [e.as_dict() for e in events]
        r = requests.post(url, headers=headers, json=data, params=params)
        if r.status_code == 400 and r.content and r.json():
            raise ValueError("Server event validation failed. Server message was: {}".format(r.json()))
        try:
            r.raise_for_status()
        except (HTTPError, RequestError) as e:
            if num_retries > 0:
                return self._send_events_with_retry(events, validate=validate, num_retries=num_retries - 1)
            raise IOError("Unable to send events to Haro. Original error was: {}".format(e))
        data = r.json()
        errors = data.get('errors', [])
        num_sent = data.get('count', 0)
        return num_sent, errors

    def _build_request_headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-ID": self.api_id,
            "X-API-KEY": self.api_key,
        }
        return headers

    def rank(self, pid, user, subset=None, top=None, include_scores=False, name=None):
        """
        Return a ranking prediction for a given user.
        Args:
            pid (str): Predictor identifier
            user (str): User id. Must match the user id sent in events
            subset (list of str): list of items or context values to limit the ranking results to
            top (int or None): Limit the returned ranked values to top k.
            include_scores (bool): when true, the API will also send relative item scores
            name (str or None): Optional custom name for the predictor
        Returns:
            RankResult: containing sorted items or categorical context
                , and if include_scores is True, list of relative scores
                   "
        """
        url = posixpath.join(_PREDICTION_API_ENDPOINT, _PREDICTION_API_VERSION,
                             "rank", pid, "user", user, "")
        headers = self._build_request_headers()
        params = {}
        if subset is not None:
            params['subset'] = json.dumps(subset)
        if top is not None:
            params['top'] = top
        if include_scores is not None:
            params['include_scores'] = include_scores
        if name is not None:
            params['name'] = name
        r = requests.get(url, headers=headers, params=params)
        try:
            r.raise_for_status()
        except (HTTPError, RequestError) as e:
            raise IOError("Unable to make a rank prediction. Error was: {}".format(e))
        response = r.json()
        return RankResult(entities=response['entities'],
                          scores=response.get('scores', None),
                          pid=pid, name=name,
                          meta=_get_meta_from_response_headers(r))

    def predict(self, pid, user, name=None):
        """
        Return a numeric prediction for a given user.

        Args:
            pid (str): Predictor identifier
            user (str): User id. Must match the user id sent in events
            name (str or None): Optional custom name for the predictor
        Returns:
            NumericPredictionResult: containing the predicted value
                   "
        """
        url = posixpath.join(_PREDICTION_API_ENDPOINT, _PREDICTION_API_VERSION,
                             "predict", pid, "user", user, "")
        headers = self._build_request_headers()
        params = {}
        if name is not None:
            params['name'] = name
        r = requests.get(url, headers=headers, params=params)
        try:
            r.raise_for_status()
        except (HTTPError, RequestError) as e:
            raise IOError("Unable to make a numerical prediction. Error was: {}".format(e))
        response = r.json()
        return NumericPredictionResult(value=response['value'], pid=pid, name=name,
                                       meta=_get_meta_from_response_headers(r))

    def anticipate(self, pid, user, name=None):
        """
        Return an anticipate prediction for a given user.

        Args:
            pid (str): Predictor identifier
            user (str): User id. Must match the user id sent in events
            name (str or None): Optional custom name for the predictor
        Returns:
            AnticipateResult: containing the probability of the anticipated event happening for
            the given user
                   "
        """
        url = posixpath.join(_PREDICTION_API_ENDPOINT, _PREDICTION_API_VERSION,
                             "anticipate", pid, "user", user, "")
        headers = self._build_request_headers()
        params = {}
        if name is not None:
            params['name'] = name
        r = requests.get(url, headers=headers, params=params)
        try:
            r.raise_for_status()
        except (HTTPError, RequestError) as e:
            raise IOError("Unable to make an anticipate prediction. Error was: {}".format(e))
        response = r.json()
        return AnticipateResult(value=response['value'], pid=pid, name=name,
                                meta=_get_meta_from_response_headers(r))

    def custom(self, pid, user, name=None):
        """
        Returns a custom prediction for a given user [advanced usage]

        Args:
            pid (str): Predictor identifier
            user (str): User id. Must match the user id sent in events
            name (str or None): Optional custom name for the predictor
        Returns:
            CustomResult: containing the custom value
                   "
        """
        url = posixpath.join(_PREDICTION_API_ENDPOINT, _PREDICTION_API_VERSION,
                             "custom", pid, "user", user, "")
        headers = self._build_request_headers()
        params = {}
        if name is not None:
            params['name'] = name
        r = requests.get(url, headers=headers, params=params)
        try:
            r.raise_for_status()
        except (HTTPError, RequestError) as e:
            raise IOError("Unable to make a custom prediction. Error was: {}".format(e))
        response = r.json()
        return CustomResult(value=response['value'], pid=pid, name=name,
                            meta=_get_meta_from_response_headers(r))

    def all_predictions(self, user, top=None, include_scores=False):
        """
        Returns all predictions for given user from the current active predictors

        Args:
            user (str): User id. Must match the user id sent in events
            top (int or None): Limit the returned ranked values to top k.(for rank predictors)
            include_scores (bool): If true, the API will also send relative item scores (for rank predictors)
        Returns:
            list of PredictionResult: list of prediction results from active predictors
        """
        url = posixpath.join(_PREDICTION_API_ENDPOINT, _PREDICTION_API_VERSION,
                             "all-predictions", "user", user, "")
        headers = self._build_request_headers()
        params = {}
        if top is not None:
            params['top'] = top
        if include_scores is not None:
            params['include_scores'] = include_scores
        r = requests.get(url, headers=headers, params=params)
        try:
            r.raise_for_status()
        except (HTTPError, RequestError) as e:
            raise IOError("Unable to get all user predictions. Error was: {}".format(e))
        response = r.json()
        prediction_results = []
        for result in response:
            pid = result['pid']
            pred_type = self._get_predictor_type_from_pid(pid)
            if pred_type == "rank":
                prediction_result = RankResult(
                    entities=result['predictions']['entities'],
                    scores=result['predictions'].get('scores', None),
                    pid=pid, name=result['name'])
            elif pred_type == 'predict':
                prediction_result = NumericPredictionResult(
                    value=result['predictions']['value'],
                    pid=pid, name=result['name'])
            elif pred_type == 'anticipate':
                prediction_result = AnticipateResult(
                    value=result['predictions']['value'],
                    pid=pid, name=result['name'])
            elif pred_type == 'custom':
                prediction_result = CustomResult(
                    value=result['predictions']['value'],
                    pid=pid, name=result['name'])
            else:
                continue
            prediction_results.append(prediction_result)
        return prediction_results

    @staticmethod
    def _get_predictor_type_from_pid(pid):
        for predictor_type in ('rank', 'predict', 'anticipate', 'custom'):
            if pid.startswith(predictor_type):
                return predictor_type
        raise ValueError("Unknown predictor type in pid: {}".format(pid))


class PredictionResult(object):
    """
    Represents a single  prediction for a user
    """

    def __init__(self, pid, name, meta=None):
        """
        Args:
            pid (str): Predictor identifier that generated this prediction
            name (str): Predictor custom that generated this prediction
            meta (dict or None): additional meta information about the prediction
        """
        self.pid = pid
        self.name = name
        self.meta = meta if meta is not None else {}


class RankResult(PredictionResult):
    """
    Represents a single ranking prediction for a user
    """

    def __init__(self, entities, scores, pid, name, meta=None):
        """
        Args:
            entities (list of str): list of item or categorical context values.
            scores (list of float or None): list of relative scores, populated when include_scores is used.
            pid (str): Predictor identifier that generated this prediction
            name (str): Predictor custom that generated this prediction
            meta (dict or None): additional meta information about the prediction
        """
        super(RankResult, self).__init__(pid, name, meta)
        self.entities = entities
        self.scores = scores

    def __str__(self):
        return "RankResult(entities={self.entities}, scores={self.scores})".format(self=self)


class NumericPredictionResult(PredictionResult):
    """
    Represents a single numerical prediction for a user
    """

    def __init__(self, value, pid, name, meta=None):
        """
        Args:
            value (float): numerical value predicted
            pid (str): Predictor identifier that generated this prediction
            name (str): Predictor custom that generated this prediction
            meta (dict or None): additional meta information about the prediction
        """
        super(NumericPredictionResult, self).__init__(pid, name, meta)
        self.value = value

    def __str__(self):
        return "NumericPredictionResult(value={self.value})".format(self=self)


class AnticipateResult(PredictionResult):
    """
    Represents a single anticipate prediction for a user
    """

    def __init__(self, value, pid, name, meta=None):
        """
        Args:
            value (float): probability of anticipated event happening for the given user
            pid (str): Predictor identifier that generated this prediction
            name (str): Predictor custom that generated this prediction
            meta (dict or None): additional meta information about the prediction
        """
        super(AnticipateResult, self).__init__(pid, name, meta)
        self.value = value

    def __str__(self):
        return "AnticipateResult(value={self.value})".format(self=self)


class CustomResult(PredictionResult):
    """
    Represents a custom prediction for a user [for advanced usage]
    """

    def __init__(self, value, pid, name, meta=None):
        """
        Args:
            value (float): numerical value predicted
            pid (str): Predictor identifier that generated this prediction
            name (str): Predictor custom that generated this prediction
            meta (dict or None): additional meta information about the prediction
        """
        super(CustomResult, self).__init__(pid, name, meta)
        self.value = value

    def __str__(self):
        return "CustomResult(value={self.value})".format(self=self)


def _get_meta_from_response_headers(response):
    """
    Returns:
        dict: meta data extracted from the response headers
    """
    return dict((k.replace("X-", "", 1), v)
                for (k, v) in response.headers.items() if k.startswith("X-"))
