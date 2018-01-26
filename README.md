# haro-python-sdk
[Haro.ai](https://haro.ai/) Python Library

This library is a thin wrapper around Haro's Events and Prediction API.
See the [Haro.ai](https://haro.ai/) documentation for more details. 

## Example Usage:

### Events API
    from haro.api import HaroAPIClient, Event
    api =  HaroAPIClient(api_id='your api id', api_key='your apii key')
    now = int(datetime.datetime.utcnow().timestamp() * 1000)
    e = Event(id="eid-34812", user="user-31415", action="watch", item="m-9754", 
               timestamp=now,  context={"duration_seconds": 35})
    api.send_events([e])


### Prediction API

    from haro.api import HaroAPIClient
    api =  HaroAPIClient(api_id='your api id', api_key='your apii key')
    r = api.rank(pid='rank-items-for-action-watch', user='u-314-15', include_scores=True, top=5)
    print(r.entities)
    > ["m-4257”, "m-8762”,  "m-2485”, "m-4679”, "m-9461”]
    print(r.scores)
    > [0.725, 0.642, 0.613, 0.546, 0.532]
    
     
### Running the unittests
    > python setup.py test