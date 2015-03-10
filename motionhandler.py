#!/usr/bin/env python

from hotqueue import HotQueue
import redis
import json
# from pimotionupload import PiUpload
from datetime import datetime
from time import sleep
import sys, gc
import subprocess

sys.stdout.write("Starting motionhandler.py\n")

queue = HotQueue("uploadqueue", serializer=json, host="localhost", port=6379, db=0)
eventlog = redis.Redis("localhost")

time = datetime.now()
currentdate = "%04d-%02d-%02d" % (time.year, time.month, time.day)
currentevent = 1

eventlog.setnx("eventdate", currentdate)
eventlog.setnx("event", currentevent)

eventdate = eventlog.get("eventdate")
currentevent = int(eventlog.get("event"))
event = "EVT_%02d" % currentevent
sys.stdout.write(event + "\n")


for item in queue.consume():
  if item['MsgType'] == 'startevent':
    eventdate = eventlog.get("eventdate")
    time = datetime.now()
    currentdate = "%04d-%02d-%02d" % (time.year, time.month, time.day)
    if currentdate != eventdate:
      sys.stdout.write("New date " + currentdate + "\n")
      eventdate = currentdate
      eventlog.set("eventdate", eventdate)
      currentevent = 1
    else:
      currentevent += 1  

    eventlog.set("event", currentevent)
    event = "EVT_%02d" % currentevent
    sys.stdout.write("startevent: " + event + "\n")

  elif item['MsgType'] == 'stopevent':
    sys.stdout.write(item['MsgType'] + "\n")

  elif item['MsgType'] == 'upload':
    sys.stdout.write("Upload request: " + item['File'] + "\n")
    # PiUpload(item['File'], eventdate, event)
    proc = subprocess.Popen("python -u pimotionupload.py %s %s %s" % (item['File'], eventdate, event), shell=True)
    proc.wait()
    sleep(1)

  elif item['MsgType'] == 'forced_capture':
    sys.stdout.write("Forced Upload request: " + item['File'] + "\n")
    time = datetime.now()
    forcedate = "%04d-%02d-%02d" % (time.year, time.month, time.day)
    # PiUpload(item['File'], forcedate, "Request")
    proc= subprocess.Popen("python -u pimotionupload.py %s %s %s" % (item['File'], forcedate, "Request"), shell=True)
    proc.wait()

  elif item['MsgType'] == 'thumb_capture':
    sys.stdout.write("Forced thumbnail request: " + item['File'] + "\n")
    time = datetime.now()
    time = datetime.now()
    forcedate = "%04d-%02d-%02d" % (time.year, time.month, time.day)
    # PiUpload(item['File'], forcedate, "Request")
    proc= subprocess.Popen("python -u pimotionupload.py %s %s %s" % (item['File'], forcedate, "Request"), shell=True)
    proc.wait()

  elif item['MsgType'] == 'garbagedisposal':
    sys.stdout.write(item['MsgType'] + "\n")
    collected = gc.collect()
    sys.stdout.write("Collected %d objects\n" % collected)
    
  else:
    print "Unknown msg"
    sys.stdout.write("Unknown msg: " + item['MsgType'] + "\n")

