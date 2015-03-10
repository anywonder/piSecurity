#!/usr/bin/env python

from hotqueue import HotQueue
import redis
import json
#from pimotionupload import PiUpload
from datetime import datetime


queue = HotQueue("uploadqueue", serializer=json, host="localhost", port=6379, db=0)
eventlog = redis.Redis("localhost")

time = datetime.now()
currentdate = "%04d-%02d-%02d" % (time.year, time.month, time.day)
currentevent = 1

eventlog.setnx("eventdate", currentdate)
eventlog.setnx("event", currentevent)

eventdate = eventlog.get("eventdate")
currentevent = eventlog.get("event")
event = "EVT_%d" % int(currentevent)

for item in queue.consume():
  if item['MsgType'] == 'startevent':
    print "startevent: " + event

  elif item == 'stopevent':
    print item['MsgType']
  else:
    print "Upload request: " + item['MsgType']


