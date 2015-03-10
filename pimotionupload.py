#!/usr/bin/python

import httplib2
import os
import json as simplejson
import sys
import magic

from apiclient.discovery import build
from apiclient.http import MediaFileUpload
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
from apiclient import errors
from time import sleep

# if len(sys.argv) < 3:
#   print "Invalid parameters!"
#   print "Usage: pimotionupload.py <filename> <folder>"
#   quit()


def FindSubFolder(drive, folder, parent):
  query = "not trashed and mimeType = 'application/vnd.google-apps.folder' and '" + parent['id'] + "'" + " in parents and title = '" + folder + "'"
  exists = drive.files().list(q=query).execute()['items']
  if len(exists):
    return exists[0]
  else:
    return None


def FindRootFolder(drive, folder):
  query = "mimeType = 'application/vnd.google-apps.folder' and not trashed and title = '" + folder + "'"
  exists = drive.files().list(q=query).execute()['items']
  if len(exists):
    return exists[0]
  else:
    return None
 
def FindFile(drive, filename, folder=None):
  query = "not trashed and title = '" + filename + "'"
  if folder != None:
    query += " and '" + folder['id'] + "' in parents"
  exists = drive.files().list(q=query).execute()['items']
  if len(exists):
    return exists[0]
  else:
    return None

def UploadJPEG(drive, filename, folder=None):
  jpgfile = FindFile(drive, filename, folder)
  if jpgfile == None:
    mime = magic.Magic(mime=True)
    filemimetype = mime.from_file(filename)
    media_body = MediaFileUpload(filename, mimetype=filemimetype, resumable=True)
    body = {
      'title': filename,
      'description': 'A test jpeg',
      'mimeType': filemimetype
      # 'mimeType': 'image/jpeg'
    }

    if folder != None:
      body['parents'] = [{'id': folder['id']}]
  
    jpgfile = drive.files().insert(body=body, media_body=media_body).execute()
    # print "Uploaded " + filename
    sys.stdout.write("Uploaded " + filename + "\n")
  else:
    # print filename + " exists already"
    sys.stdout.write(filename + " exists already\n")

  return jpgfile

def CreateFolder(drive, foldername, parentfolder=None):
  body = {
    'title': foldername,
    'mimeType': "application/vnd.google-apps.folder"
  }

  if parentfolder != None:
    body['parents'] = [{'id': parentfolder['id']}]
    
  folder = drive.files().insert(body=body).execute()
  # print "Created Folder: " + folder['id']
  sys.stdout.write("Created Folder: " + folder['id'] + "\n")
  return folder


def PiUpload(filename, foldername, eventname):
  # Copy your credentials from the APIs Console
  CLIENT_ID = '1014795029681-j5sc2aap4s1q4j7tt0326t3qn7uib36o.apps.googleusercontent.com'
  CLIENT_SECRET = 'UQT4eJTBfwN007TTtFGIVkKn'

  # Check https://developers.google.com/drive/scopes for all available scopes
  OAUTH_SCOPE = 'https://www.googleapis.com/auth/drive'

  # Redirect URI for installed apps
  REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'

  # Path to the file to upload
  JPEGNAME = filename # sys.argv[1]
  DATEFOLDER = foldername
  EVENTFOLDER = eventname # sys.argv[2]

  PIMOTION_FOLDER = 'PiMotion'
  # Try to read the credentials first
  storage = Storage('pimotion.cred')
  credentials = storage.get()

  if credentials == None:
    # Run through the OAuth flow and retrieve credentials
    flow = OAuth2WebServerFlow(CLIENT_ID, CLIENT_SECRET, OAUTH_SCOPE, REDIRECT_URI)
    authorize_url = flow.step1_get_authorize_url()
    print 'Go to the following link in your browser: ' + authorize_url
    code = raw_input('Enter verification code: ').strip()
    credentials = flow.step2_exchange(code)

    # store the credentials
    storage.put(credentials)

  try:
    # Create an httplib2.Http object and authorize it with our credentials
    http = httplib2.Http()
    http = credentials.authorize(http)

    drive = build('drive', 'v2', http=http)

    # Create PiMotion folder if it does not exist
    pifolder = FindRootFolder(drive, PIMOTION_FOLDER)

    if pifolder == None:
      # Create the PiMotion folder
      pifolder = CreateFolder(drive, "PiMotion")

    # Create a sub folder of pimotion
    datefolder =  FindSubFolder(drive, DATEFOLDER, pifolder)

    if datefolder == None:
      datefolder = CreateFolder(drive, DATEFOLDER, pifolder)

    # Create a event folder of which is a sub folder of datefolder
    eventfolder =  FindSubFolder(drive, EVENTFOLDER, datefolder)

    if eventfolder == None:
      eventfolder = CreateFolder(drive, EVENTFOLDER, datefolder)

    # Insert a file in datefolder
    file = UploadJPEG(drive, JPEGNAME, eventfolder)
    
    # Delete the file
    os.remove(JPEGNAME)

    return True

  except errors.HttpError, e:
    sys.stderr.write("Failed to upload\n")

  return False



if len(sys.argv) != 4:
  sys.stderr.write("Invalid parameters %d\n" % (len(sys.argv)) )
  sys.exit("usage: pimotionupload.py <filename> <datedir> <eventdir>")

retryCount = 3

while retryCount > 0:
  retryCount = retryCount - 1
  if True == PiUpload(sys.argv[1], sys.argv[2], sys.argv[3]):
    break
  else:
    sys.stderr.write("Failed PiUpload %d\n" % retryCount)
    sleep(10)


