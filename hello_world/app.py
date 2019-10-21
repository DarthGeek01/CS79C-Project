import json
import boto3
import uuid
import secrets
import datetime

from passlib.hash import pbkdf2_sha256

USERS_TABLE_NAME = "FinalProjUsers"
POSTS_TABLE_NAME = "FinalProjPosts"
NO_SUCCESS = {'success': False}

db = None



"""Function to create user in dynamo

Parameters
----------
email: user email, required
passwd: user password, required

Returns
----------
dict containing success value, user id, user session token

"""
def create_user(email, passwd):
    # Check if user email is already taken
    resp = db.get_item(
        TableName=USERS_TABLE_NAME,
        Key={
            'email': {'S': email}
        }
    )
    if resp['items']:
        return {'success': False}

    # Hash user password using pbkdf2
    pwd_hash = pbkdf2_sha256.hash(passwd)
    user_id = str(uuid.uuid1())

    # Generate random secret, then hash it and return to client as session token
    session_secret = secrets.token_urlsafe(16)
    session_hash = pbkdf2_sha256.hash(session_secret)

    # Session tokens expire 1 week from creation date
    # Create datetime str for expiration date, and store with current secret
    token_expire_time = str(datetime.datetime.now() + datetime.timedelta(days=7))

    db.put_item(TableName=USERS_TABLE_NAME, Item={
        'uuid': user_id,
        'email': email,
        'pwd_hash': pwd_hash,
        'session_secret': session_secret,
        'expire_time': token_expire_time
    })

    return {
        'success': True,
        'uuid': user_id,
        'token': session_hash
    }


"""Function to create user in dynamo

Parameters
----------
email: user email, required
passwd: user password, required

Returns
----------
dict containing success value, uuid, session token

"""
def login(email, passwd):
    resp = db.get_item(
        TableName=USERS_TABLE_NAME,
        Key={
            'email': email
        }
    )
    item = resp['Item']
    # Fail if user does not exist
    if not item:
        return NO_SUCCESS

    # Fail if verification fails
    if not pbkdf2_sha256.verify(passwd, item['pwd_hash']):
        return NO_SUCCESS

    # Create new session secret, hash, expire time
    session_secret = secrets.token_urlsafe(16)
    session_hash = pbkdf2_sha256.hash(session_secret)
    token_expire_time = str(datetime.datetime.now() + datetime.timedelta(days=7))

    db.update_item(
        TableName=USERS_TABLE_NAME,
        Key=item,
        UpdateExpression="set session_secret = :s, expire_time = :t",
        ExpressionAttributeValues={
            ':s': session_secret,
            ':t': token_expire_time
        }
    )

    return {
        'success': True,
        'uuid': item['uuid'],
        'token': session_hash
    }


def verify_session(uuid, token):
    resp = db.get_item(
        TableName=USERS_TABLE_NAME,
        Key={
            'uuid': uuid
        }
    )
    item = resp['Item']
    # Fail if user does not exist
    if not item:
        return False

    return pbkdf2_sha256.verify(item['session_secret'], token)


def create_post(title, body_text, uuid, token):
    if not verify_session(uuid, token):
        return NO_SUCCESS

    # Not filtering for duplicate posts because that makes no sense to me
    upid = uuid.uuid1()
    db.put_item(
        Table=POSTS_TABLE_NAME,
        Item={
            'upid': upid,
            'title': title,
            'body_text': body_text,
            'users_uvote': [uuid],
            'users_dvote': []
        }
    )


def upvote(uuid, upid, token, type):
    if not verify_session(uuid, token):
        return NO_SUCCESS

    type1 = "users_upvote" if type else "users_downvote"
    type2 = "users_downvote" if type else "users_upvote"


    resp = db.get_item(
        Table=POSTS_TABLE_NAME,
        Key={
            'upid': upid
        }
    )
    item = resp['Item']
    if not item:
        return NO_SUCCESS

    # Remove opposite vote, if it's there
    if uuid in item[type2]:
        item[type2].remove(uuid)
    # If we've already cast a vote of this type, remove it
    if uuid in item[type1]:
        item[type1].remove(uuid)
    # Else, cast a vote of this type
    else:
        item[type1].append(uuid)

    # Just overwrite
    db.put_item(Table=POSTS_TABLE_NAME, Item=item)




def lambda_handler(event, context):
    global db
    db = boto3.client("dynamodb")

    path = event['path']
    method = event['method']

    

    return {
        "statusCode": 200,
        "body": json.dumps(event),
    }
