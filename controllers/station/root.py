import logging
from controllers.base import BaseHandler

class RootHandler(BaseHandler):
	
	@property
	def is_admin(self):
		if not hasattr(self, "_is_admin"):
			self._is_admin = False
			if(self.user_proxy):
				page_id = self.station_proxy.station.key().name()
				if(self.user_proxy.is_admin_of(page_id)):
					self._is_admin = True
		return self._is_admin
	
	def render(self, template_path, template_values):
		if template_values:
			self._template_values = template_values
		else:
			self._template_values = {}
		
		try:
			self._template_values["is_admin"] = self.is_admin
			self._template_values["station_proxy"] = self.station_proxy	
			self._template_values["number_of_visits"] = self.station_proxy.number_of_visits

			if self.station_proxy.station.type == 'user':
				self._template_values["is_page"] = False
			else:
				self._template_values["is_page"] = True

		except (AttributeError, TypeError):
			# in case of a 404 error
			logging.info("No station proxy")
		
		super(RootHandler, self).render(template_path, self._template_values)