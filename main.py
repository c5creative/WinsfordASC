# Winsford ASC Google AppEngine App
#   main.py
#   Entry point for most http requests.
#
# Copyright (C) 2014 Oliver Wright
#    oli.wright.github@gmail.com
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program (file LICENSE); if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.



import logging

import webapp2

import helpers

from swimmer import Swimmer
from swim import Swim
from swim import ScrapeSplits
from event import short_course_events
from event import long_course_events
from race_time import RaceTime
from static_data import StaticData

# Member check URL: https://www.swimmingresults.org/membershipcheck/member_details.php?myiref=smith
# Swim list for member URL: http://www.swimmingresults.org/individualbest/personal_best_time_date.php?back=individualbest&tiref=892569&mode=A&tstroke=1&tcourse=S

# http://www.swimmingresults.org/individualbest/personal_best_time_date.php?back=individualbest&tiref=526253&mode=A&tstroke=1&tcourse=S

# If we find a club member listing, then the club property is likely to be "targetclub" like https://www.swimmingresults.org/clubofficers/officers_list.php?targetclub=FSSTESXQ
# although that looks like it's hashed in some way.   Winsford's code is WINNCHRN
    
class PersonalBests(webapp2.RequestHandler):
  def get(self):
    asa_numbers = self.request.get('asa_numbers', allow_multiple=True)
    num_swimmers = len( asa_numbers )
    self.response.headers['Content-Type'] = 'text/plain'
    if num_swimmers == 0:
      # Show error page
      self.response.out( "Missing asa_numbers parameters" )
    else:
      # Collate list of swimmers
      swimmers = []
      for asa_number in asa_numbers:
        swimmer = Swimmer.get( "Winsford", int(asa_number) )
        if swimmer is not None:
          swimmers.append( swimmer )
      
      def listEvents( events ):
        for event in events:
          self.response.out.write( event.to_string() )
          # Write a comma separated list with the PB in seconds of each requested swimmer.
          # Leave blank if the swimmer has no PB for this event.
          for swimmer in swimmers:
            self.response.out.write(',')
            swim = Swim.fetch_pb( swimmer, event )
            if swim is not None:
              self.response.out.write( str( swim.race_time ) + "," + swim.meet + "," + swim.date.strftime( "%d/%m/%Y" ) + "," + swim.create_swim_key_str() )
          self.response.out.write( '\n' )

      listEvents( short_course_events )
      listEvents( long_course_events )
        
class GetSwimmerList(webapp2.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.out.write( StaticData.get_swimmer_list() )
        
class GetSwimDetails(webapp2.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain'
    swim_key_str = self.request.get('swim')
    if swim_key_str is None:
      self.response.out.write( "Missing swim key" )
      return
    swim = Swim.get_from_key_str( swim_key_str )
    if swim is None:
      self.response.out.write( "Unrecognised swim key: " + swim_key_str )
      return
    if swim.get_asa_swim_id() is not None:
      # This swim has an ASA swim id, so that means there should be
      # split times available for it.
      if not hasattr(swim, 'splits' ):
        # Try and get them from swimmingresults.org
        ScrapeSplits( swim )

    self.response.out.write( str( swim ) )

app = webapp2.WSGIApplication([
  ('/personal_bests', PersonalBests),
  ('/swimmer_list', GetSwimmerList),
  ('/swim_details', GetSwimDetails),
])