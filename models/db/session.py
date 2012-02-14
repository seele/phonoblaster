from calendar import timegm

from google.appengine.ext import db

from models.db.user import User
from models.db.station import Station

class Session(db.Model):
	# key_name = channel_id
	channel_token = db.StringProperty(required = True)
	user = db.ReferenceProperty(User, required = False, collection_name = "sessionUser")
	created = db.DateTimeProperty(auto_now_add = True)
	
	@staticmethod
	def get_extended_sessions(sessions):
		user_keys = [Session.user.get_value_for_datastore(s) for s in sessions]
		users = User.get(user_keys)
		
		extended_sessions = [Session.get_extended_session(s, u) for s, u in zip(sessions, users)]
		return extended_sessions
	
	@staticmethod
	def get_extended_session(session, user):
		if(user):	
			extended_session = {
				"key_name": session.key().name(),
				"created": timegm(session.created.utctimetuple()),
				"listener_key_name": user.key().name(),
				"listener_name": user.first_name + " " + user.last_name,
				"listener_url": "/user/" + user.key().name(),
			}
		else:
			extended_session = {
				"key_name": session.key().name(),
				"created": timegm(session.created.utctimetuple()),
				"user_key_name": None,
				"user_name": None,
				"listener_url": None,
			}
			
		return extended_session
