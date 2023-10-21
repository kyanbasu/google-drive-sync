import pickle
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from tabulate import tabulate

import shutil
import io
from googleapiclient.http import MediaIoBaseDownload


from os import listdir
from os.path import isfile, getmtime

import time
from datetime import datetime
date_format = "%Y-%m-%dT%H:%M:%S.%fZ" 
#usage
#datetime.now().strftime(date_format) -                               to this format
#datetime.strptime('2008-09-26T01:51:42.000Z', date_format) - from this format

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/drive']

sync_folder = '15F0pDw6GSIgD78nmGMWOfqAeDM7c_EET'
local_sync_folder = './test'
if not os.path.exists(local_sync_folder):
    local_sync_folder = './sync'

start_time = time.time()

def get_gdrive_service():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials-1kyanbasu.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    # return Google Drive API service
    return build('drive', 'v3', credentials=creds)

service = get_gdrive_service()

def list_files(items):
    """given items returned by Google Drive API, prints them in a tabular way"""
    if not items:
        # empty drive
        print('No files found.')
    else:
        rows = []
        for item in items:
            # get the File ID
            id = item["id"]
            # get the name of file
            name = item["name"]
            try:
                # parent directory ID
                parents = item["parents"]
            except:
                # has no parrents
                parents = "N/A"
            try:
                # get the size in nice bytes format (KB, MB, etc.)
                size = sizeof_fmt(int(item["size"]))
            except:
                # not a file, may be a folder
                size = "N/A"
            # get the Google Drive type of file
            mime_type = item["mimeType"]
            # get last modified date time
            modified_time = item["modifiedTime"]
            # append everything to the list
            rows.append((id, name, parents, size, mime_type, modified_time))
        print("Files:")
        # convert to a human readable table
        table = tabulate(rows, headers=["ID", "Name", "Parents", "Size", "Type", "Modified Time"])
        # print the table
        print(table)

cloud_tree = {}
local_tree = {}

### Cloud

def get_cloud():
    # Call the Drive v3 API
    results = service.files().list(
        pageSize=100, fields="nextPageToken, files(id, name, mimeType, parents, modifiedTime)").execute()
    items = results.get('files', [])
    #print(items)
    get_tree_from_cloud(items)

    while True:
        try:
            #print(f"page token {results['nextPageToken']}")
            results = service.files().list(
            pageSize=100, pageToken=results['nextPageToken'], fields="nextPageToken, files(id, name, mimeType, parents, modifiedTime)").execute()
            items = results.get('files', [])
            get_tree_from_cloud(items)
        except:
            break


    for key, item in cloud_tree.items():
        #print(item['name'], item['type'])
        path = get_cloud_path(key)
        if not item['type'].endswith('folder'):
            item['path'] = path
        else:
            item['path'] = ''

def get_tree_from_cloud(items):
    if not items:
        # empty drive
        print('No files found.')
    else:
        rows = []
        for item in items:
            #print(f"type: {item['mimeType']} parent: {item['parents'][0]} id: {item['id']} size: {size} name: {item['name']} modified: {item['modifiedTime']}")
            cloud_tree[item['id']] = {"name": item['name'], "parent": item['parents'][0], "type": item['mimeType'], "modified": datetime.timestamp(datetime.strptime(item['modifiedTime'], date_format))}

def get_cloud_path(key, curr_path=""):
    try:
        curr_path = f"/{cloud_tree[key]['name']}{curr_path}"
        if key == sync_folder:
            return ""
        if cloud_tree[key]['parent'] == sync_folder:
            return f"{curr_path}"
        return get_cloud_path(cloud_tree[key]['parent'], curr_path)
    except:
        return ""

#sync from local to cloud
def cloud_sync():
    pass
    
### Local

def get_tree_local(path=""):
    for f in listdir(local_sync_folder + "/" + path):
        if isfile(f"{local_sync_folder}/{path}{f}"):
            local_tree[f"/{path}{f}"] = {"name": f, "modified": getmtime(f"{local_sync_folder}/{path}{f}")}
        else:
            get_tree_local(f"{path}{f}/")

#sync from cloud to local 
def local_sync():
    for cf in cloud_tree:
        if cloud_tree[cf]['path'] != '' and "/".join(cloud_tree[cf]['path'].split("/")[1:]) != 'cloud_sync_config.dat':
            pth = cloud_tree[cf]['path'].split("/")[1:]
            #print(cf, pth, cloud_tree[cf]['modified'])

            c_pth = ""
            for p in pth:
                c_pth += f"/{p}"
                if not os.path.exists(local_sync_folder + c_pth):
                    if p == pth[-1]:
                        #print(f"create file: {c_pth}")
                        r = service.files().get_media(fileId=cf)
                        fh = io.BytesIO()
                        downloader = MediaIoBaseDownload(fh, r)
                        done = False
                        while done is False:
                            status, done = downloader.next_chunk()
                            #print("Download %d%%" % int(status.progress() * 100))
                        # The file has been downloaded into RAM, now save it in a file
                        fh.seek(0)
                        with open(local_sync_folder + c_pth, 'wb') as f:
                            shutil.copyfileobj(fh, f, length=131072)
                    else:
                        #print("create folder: ", end="")
                        os.mkdir(local_sync_folder + c_pth)
                        #print(c_pth)
                    os.utime(local_sync_folder + c_pth, (time.time(), cloud_tree[cf]['modified']))
                else:
                    #get modification time
                    #print(f"{p} local: {datetime.fromtimestamp(os.path.getctime(local_sync_folder + c_pth)).strftime(date_format)} {datetime.fromtimestamp(os.path.getmtime(local_sync_folder + c_pth)).strftime(date_format)} \ncloud: {datetime.fromtimestamp(cloud_tree[cf]['modified']).strftime(date_format)}")
                    pass

### Main

def main():

    get_cloud()
    get_tree_local()
    #print(local_tree)
    #print(cloud_tree)
    local_sync()
    print(f"this took {(time.time() - start_time)*1000} ms")

def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

if __name__ == '__main__':
    main()