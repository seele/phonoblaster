import logging
import re
import django_setup
from django.utils import simplejson as json

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api.taskqueue import Task

from controllers import config
from models.api.station import StationApi

class ConnectHandler(webapp.RequestHandler):
	def post(self):
		channel_id = str(self.request.get('from'))
		logging.info("%s is ready to receive messages" %(channel_id))
		
		# Init station proxy
		m = re.match(r"(\w+).(\w+)", channel_id)
		shortname = m.group(1)
		station_proxy = StationApi(shortname)
		
		extended_session = station_proxy.add_to_sessions(channel_id)
		
		# Add a taskqueue to warn everyone
		new_session_data = {
			"entity": "session",
			"event": "new",
			"content": extended_session,
		}
		task = Task(
			url = "/taskqueue/multicast",
			params = {
				"station": config.VERSION + "-" + shortname,
				"data": json.dumps(new_session_data)
			}
		)
		task.add(queue_name="sessions-queue")


application = webapp.WSGIApplication([
	(r"/_ah/channel/connected/", ConnectHandler),
], debug=True)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
    main()