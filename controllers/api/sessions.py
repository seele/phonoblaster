import logging

from datetime import datetime
from datetime import timedelta

from random import randrange
from calendar import timegm
from time import gmtime

import json

from google.appengine.api import channel

from controllers.base import BaseHandler
from controllers.base import login_required

from models.db.session import Session
from models.api.station import StationApi

class ApiSessionsHandler(BaseHandler):
	def get(self):
		shortname = self.request.get("shortname")
		station_proxy = StationApi(shortname)
		
		if(station_proxy.station):		
			extended_sessions = station_proxy.sessions
			sessions_data = {
				"sessions": extended_sessions,
			}
			self.response.out.write(json.dumps(sessions_data))
		else:
			self.error(404)
		
	def post(self):
		shortname = self.request.get("shortname")
		station_proxy = StationApi(shortname)
		station = station_proxy.station 
		
		output = {}
		if(station):
			# Increment visits counter 
			station_proxy.increment_visits_counter()
			
			# Channel ID and token generation
			time_now = str(timegm(gmtime()))
			random_integer = str(randrange(1000))
			new_channel_id = shortname + "." + time_now + random_integer
			new_channel_token = channel.create_channel(new_channel_id)
			
			listener_key = None
			if(self.user_proxy):
				listener_key = self.user_proxy.user.profile.key()
			
			# Put new session in datastore
			new_session = Session(
				key_name = new_channel_id,
				channel_token = new_channel_token,
				listener = listener_key,
				host = station.key(),
			)
			new_session.put()
			logging.info("New session saved in datastore")

			output = {
				"channel_id": new_channel_id,
				"channel_token": new_channel_token,
			}
			self.response.out.write(json.dumps(output))
		else:
			self.error(404)
			