#!/usr/bin/env python

import StringIO
import subprocess, shlex
import os
import time
from datetime import datetime, time, timedelta
from PIL import Image
import ImageChops
from hotqueue import HotQueue
import redis
import json
from time import sleep
import sys, gc
import ephem
import signal
import pipan


# Initialise the Message Queue and persistent store
queue = HotQueue("mymotionqueue", host="localhost", port=6379, db=0)
detectStatus = redis.Redis("localhost")

detectStatus.setnx("motionstatus", "monitoring")

uploadqueue = HotQueue("uploadqueue", serializer=json, host="localhost", port=6379, db=0)

pantilt = pipan.PiPan()
default_pan = 208
default_tilt = 165
pantilt.do_pan(default_pan)
pantilt.do_tilt(default_tilt)



# Motion detection settings:
# Threshold (how much a pixel has to change by to be marked as "changed")
# Sensitivity (how many changed pixels before capturing an image)
# ForceCapture (whether to force an image to be captured every forceCaptureTime seconds)
trigger_sensitivity = 7
event_sensitivity = 2
sensitivity = 20
forceCaptureTime = 60 * 60 # Once an hour

# File settings
saveWidth = 1280
saveHeight = 960

# Capture Time
ct = datetime.now()
thumbmask = Image.open("mask_garage.bmp").convert("L")


def getnextsunrise():
  o = ephem.Observer()
  o.lat='54.46'
  o.long='-6'
  s=ephem.Sun()
  s.compute()
  return ephem.localtime(o.next_rising(s)).time()

def getnextsunset():
  o = ephem.Observer()
  o.lat='54.46'
  o.long='-6'
  s=ephem.Sun()
  s.compute()
  return ephem.localtime(o.next_setting(s)).time()


# Capture a small test image (for motion detection)
def captureTestImage():
    # command = "raspistill -w %s -h %s -t 0 -e bmp -o -" % (100, 75)
    command = "raspistill -w %s -h %s -t 1 -e bmp -vf -hf -o -" % (200, 150)
    imageData = StringIO.StringIO()
    imageData.write(subprocess.check_output(command, shell=True))
    imageData.seek(0)
    im = Image.open(imageData)
    im.paste(thumbmask, mask=thumbmask.split()[0])
    imageData.close()
    return im

# Save a full size image to disk
def saveImage(width, height, changedPixels):
    global ct
    # Record the Capture Time
    ct = datetime.now()
    filename = "capture-%04d%02d%02d-%02d%02d%02d_S%d.jpg" % (ct.year, ct.month, ct.day, ct.hour, ct.minute, ct.second, changedPixels)
    # subprocess.call("raspistill -w 1296 -h 972 -t 0 -e jpg -q 15 -vf -hf -ex sports -o %s" % filename, shell=True)
    subprocess.call("raspistill -w 1296 -h 972 -t 1 -e jpg -q 15 -vf -hf -o %s" % filename, shell=True)
    sys.stdout.write("Captured %s\n" % filename)
    uploadqueue.put({'MsgType': "upload", 'File': filename})

def forceImageCapture(width, height):
    ct = datetime.now()
    filename = "forced-%04d%02d%02d-%02d%02d%02d.jpg" % (ct.year, ct.month, ct.day, ct.hour, ct.minute, ct.second)
    subprocess.call("raspistill -w 1296 -h 972 -t 1 -e jpg -q 15 -vf -hf -o %s" % filename, shell=True)
    sys.stdout.write("Force Captured %s\n" % filename)
    uploadqueue.put({'MsgType': "forced_capture", 'File': filename})

def forceThumbCapture(width, height):
    ct = datetime.now()
    filename = "thumb-%04d%02d%02d-%02d%02d%02d.bmp" % (ct.year, ct.month, ct.day, ct.hour, ct.minute, ct.second)
    subprocess.call("raspistill -w %d -h %d -t 1 -e bmp -vf -hf -o %s" % (width, height, filename), shell=True)
    sys.stdout.write("Force Thumb %s\n" % filename)
    # im = Image.open(filename)
    # im.paste(thumbmask, mask=thumbmask.split()[0])
    # im.save(filename)
    uploadqueue.put({'MsgType': "thumb_capture", 'File': filename})


def runDetectionAndCapture():
  global sensitivity
  # Get first image
  starttime = getnextsunrise()
  stoptime = getnextsunset()
  sys.stdout.write("Sunrise: %d:%d\n" % (starttime.hour, starttime.minute))
  sys.stdout.write("Sunset: %d:%d\n" % (stoptime.hour, stoptime.minute))
  stopped = False
  
  image1= captureTestImage()
  image2 = image1
  eventactive = False
  forceCapture = False
  thumbCapture = False
  sensitivity = trigger_sensitivity
  triggerEvent = False
  garbageCollection = False

  while (True):

      item = queue.get(False)

      if item is not None:

        if item == 'monitor':
          # print "Already monitoring"  
          sys.stdout.write("Already monitoring\n")
        elif item == 'stop':
          # print "Stopping"
          sys.stdout.write("Stopping\n")
          detectStatus.set("motionstatus", "stopped")
          break
        elif item == 'force_snap':
          # print "Force a capture"
          sys.stdout.write("Force a capture\n")
          forceCapture = True
        elif item == 'thumbnail':
          # print "Force a thumb capture"
          sys.stdout.write("Force a thumb capture\n")
          thumbCapture = True
        elif item == 'reload':
          # print "TODO reload the configuration"
          sys.stdout.write("TODO reload the configuration\n")
        elif item == 'garbagecollect':
          sys.stdout.write("Garbage collection\n")
          garbageCollection = True
        elif item == 'exit':
          exit(0)
        else:
          # print "Unknown message %s" % item
          sys.stdout.write("Unknown message %s\n" % item)

      
      # Check force capture
      if forceCapture == True:
        forceCapture = False
        forceImageCapture(saveWidth, saveHeight)

      # Check thumb capture
      if thumbCapture == True:
        thumbCapture = False
        forceThumbCapture(200, 150)

      timenow = datetime.now()
      t = time(timenow.hour, timenow.minute, timenow.second)

      if t > starttime and t < stoptime:
        
        if stopped == True:
          stopped = False
          stoptime = getnextsunset()
          sys.stdout.write("Sunset: %d:%d\n" % (stoptime.hour, stoptime.minute))

        # Get comparison image
        image2 = captureTestImage()

        # Method 2 diff
        diffimage = ImageChops.difference(image1, image2)
        res = diffimage.size
        n = diffimage.load()

        newchangedPixels = 0
        newchangedPixels75 = 0

        for x in range (0, res[0]):
          for y in range (0, res[1]):
            if n[x,y] > (25,25,25):
              newchangedPixels += 1
            if n[x,y] > (75,75,75):
              newchangedPixels75 += 1

        if newchangedPixels75 > 0:
          ct = datetime.now()
          # print "Changed: %04d%02d%02d-%02d%02d%02d: 25: %d, 75: %d" % (ct.year, ct.month, ct.day, ct.hour, ct.minute, ct.second, newchangedPixels, newchangedPixels75)

        # Save an image if pixels changed
        triggerEvent = False
        if newchangedPixels75 >= sensitivity:
          if eventactive == False:
            if newchangedPixels < 2000:
              triggerEvent = True
          else:
            triggerEvent = True

        if triggerEvent == True:
            if eventactive == False:
              eventactive = True
              sensitivity = event_sensitivity
              uploadqueue.put({'MsgType': "startevent"})

            saveImage(saveWidth, saveHeight, newchangedPixels75)

        else:
          if eventactive == True:
            currenttime = datetime.now()
            if (currenttime - ct) > timedelta(seconds=120):
              # print "Event end"
              sys.stdout.write("Event end\n")
              eventactive = False
              sensitivity = trigger_sensitivity
              uploadqueue.put({'MsgType': "stopevent"})
          else:
            sleep(2)

        
        # Swap comparison buffers
        del image1
        image1 = image2

      else:
        sleep(10)
        if stopped == False:
          stopped = True
          starttime = getnextsunrise()
          sys.stdout.write("Sunrise: %d:%d\n" % (starttime.hour, starttime.minute))

      if garbageCollection == True:
        garbageCollection = False
        collected = gc.collect()
        sys.stdout.write("Collected %d objects\n" % collected)

  return


def startVideoStream():
    args = "raspivid -t 0 -h 720 -w 1080 -fps 25 -hf -vf -b 2000000 -o - | cvlc -vvv stream:///dev/stdin --sout '#standard{access=http,mux=ts,dst=:8090/cam.mp4}' :demux=h264"
    FNULL = open(os.devnull, 'w')
    proc = subprocess.Popen(args, shell=True, preexec_fn=os.setsid, stdout=FNULL, stderr=subprocess.STDOUT);
    return proc
    
def startVideoRecord():
    ct = datetime.now()
    filename = "video-%04d%02d%02d-%02d%02d%02d.mp4" % (ct.year, ct.month, ct.day, ct.hour, ct.minute, ct.second)
    args = "raspivid -t 600000 -h 720 -w 1080 -fps 25 -hf -vf -b 2000000 -o %s" % filename
    FNULL = open(os.devnull, 'w')
    proc = subprocess.Popen(args, shell=True, preexec_fn=os.setsid, stdout=FNULL, stderr=subprocess.STDOUT);
    return proc, filename

def stopVideoStream(proc, filename = None):
    os.killpg(proc.pid, signal.SIGTERM)

    if filename != None:
      uploadqueue.put({'MsgType': "forced_capture", 'File': filename})
      
    return


# Start Main application

# Need to make it read the configuration

currentStatus = detectStatus.get("motionstatus")

if currentStatus == 'monitoring':
  # print "Start Monitoring"
  sys.stdout.write("Start Monitoring\n")
  runDetectionAndCapture()
elif currentStatus == 'stopped':
  # print "Already Stopped"
  sys.stdout.write("Already Stopped\n")
else:
  print "Waiting for start message"

videoProc = None
videoRecordProc = None
recordFileName = None

while (True):

  for item in queue.consume():
    # print item
    sys.stdout.write(item + "\n")
    
    if videoProc is not None:
      if item != 'video_stream':
        stopVideoStream(videoProc)
        videoProc = None

    if videoRecordProc is not None:
      if item != 'video_record':
        stopVideoStream(videoRecordProc, recordFileName)
        videoRecordProc = None
        recordFileName = None

    if item == 'monitor':
      detectStatus.set("motionstatus", "monitoring")
      runDetectionAndCapture()
    if item == 'stop':
      detectStatus.set("motionstatus", "stopped")
    if item == 'force':
      detectStatus.set("motionstatus", "monitoring")
      runDetectionAndCapture()
    if item == 'video_stream':
      detectStatus.set("motionstatus", "streaming")
      videoProc = startVideoStream()
    if item == 'video_record':
      detectStatus.set("motionstatus", "recording")
      videoRecordProc, recordFileName = startVideoRecord()
    if item == 'reload':
      # print "TODO reload the configuration"
      sys.stdout.write("TODO reload the configuration\n")
    if item == 'exit':
      exit(0)

  
