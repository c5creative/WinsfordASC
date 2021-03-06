# Winsford ASC Google AppEngine App
#   swim.py
#   Provides the Swim ndb model, which encapsulates all data for an
#   individual's performance in a single race, including split
#   times when available.
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
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.import logging


# Google Python style guide http://google-styleguide.googlecode.com/svn/trunk/pyguide.html
#
# Naming...
# module_name, package_name, ClassName
# method_name, ExceptionName, function_name,
# GLOBAL_CONSTANT_NAME, global_var_name, instance_var_name,
# function_parameter_name, local_var_name
#
# Prefix an _ to indicate privateness

import webapp2
import logging
from google.appengine.ext import ndb
import time
import datetime
import helpers
from event import Event
#from lxml import html
#from lxml import etree
#from table_parser import TableRows
from race_time import RaceTime

def compute_swim_key_id( date, asa_number, event ):  
  # Compute an ID that is a hash of event, date and swimmer
  datehash = ((date.year - 1900) * 365) + (date.month * 31) + date.day
  hash = ((event.to_int() << 24) + datehash) ^ (asa_number << 8)
  return hash

def compute_parent_key_id( asa_number, event ):  
  # Compute a key id that is a hash of event swimmer
  return (event.to_int() << 24) ^ (asa_number << 8)
  
def create_parent_key( asa_number, event ):  
  return ndb.Key( "SwimmerEvent", compute_parent_key_id( asa_number, event ) )
    
class Split():
  def __init__(self, distance, time, interpolated):
    self.distance = distance
    self.time = time
    self.interpolated = interpolated

  def __str__(self):
    return str( self.distance ) + "m : " + str( RaceTime( self.time  ) )
    
# Encapsulates all data for an individual's performance in a single race, including split
# times when available.
class Swim(ndb.Model):
  # We try to minimise the number of NDB properties to minimise the number of read and
  # write operations that we incur, because Google App Engine's pricing is based on those
  # operations rather than something like number of bytes read and written.
  
  # We need to search by age_on_day so this needs to be a real property
  age_on_day = ndb.IntegerProperty( 'AoD', required=True )
  
  # We need to sort by race_time so this needs to be a real property
  race_time = ndb.FloatProperty( 'T', required=True )
  
  # We put everything else into a non-indexed string, so we only pay one read/write-op for it.
  # Don't use JSON because that just adds bloat for something so simple.
  # It pains me to use a string for storing things like float values, I'd much rather use
  # a binary blob, but I suppose I do need to balance coding simplicity vs. efficiency.
  data = ndb.StringProperty( "Data", indexed=False, required=True)
  
  # Creates a string that uniquely identifies this Swim.
  # The key string can be used with get_from_key_str to retrieve this Swim
  def create_swim_key_str( self ):
    # Key string format is <parent_key_id>_<swim_key_id>
    return str( compute_parent_key_id( self.asa_number, self.event ) ) + "_" + str( compute_swim_key_id( self.date, self.asa_number, self.event ) )

  # Retrieves a Swim from the database given a key string that was previously
  # created with create_swim_key_str
  @classmethod
  def get_from_key_str( cls, key_str ):
    # Split into parent key id and swim key id
    tokens = key_str.split( "_" )
    if len( tokens ) != 2:
      logging.error( "Failed to split swim key string" )
      return
    parent_key_id = int( tokens[0] )
    swim_key_id = int( tokens[1] )
    swim = ndb.Key( "SwimmerEvent", parent_key_id, "Swim", swim_key_id ).get()
    if swim is not None:
      swim.unpack_data()
    return swim

  # Internal helper to create most of the packed data string
  @classmethod
  def pack_data( cls, asa_number, event, date, meet, asa_swim_id ):
    data_str = "V1|" + str( asa_number ) + "|" + str(event.to_int()) + "|" + date.strftime( "%d/%m/%Y" ) + "|" + meet + "|"
    if asa_swim_id is not None:
      data_str += str( asa_swim_id )
    else:
      data_str += "-1"
    data_str += "|"
    return data_str

  # Pass split_times_from_asa as a list of known split times as floats.
  # They can have missing splits, and be either 25m or 50m splits.
  #
  # This function will attempt to create a complete list of splits in self.splits
  # by guessing the distances of the provided splits and interpolating
  # any missing splits.
  #
  # It works most of the time but has been known to go wrong on longer IM races
  # because of the non-uniformity of split times.  This should be fixable
  # with a little more thought and some heuristic data on typical split ratios
  # for IM legs.
  def fix_splits(self, split_times_from_asa):
    # The splits from the ASA website are often completely wrong in terms of
    # distance.  And there are often missing splits.
    num_25m_splits = int( self.event.getDistance() / 25 )
    any_splits_on_25m = False
    splits = [None] * num_25m_splits
    for split_time in split_times_from_asa:
      # Guess the distance of this split by looking at the whole race time
      guessed_25m_split = int( round( float( num_25m_splits ) * split_time / self.race_time ) ) - 1
      #logging.info( "Split:" + str( split_time ) + "25m: " + str( guessed_25m_split ) )
      if guessed_25m_split < 0:
        logging.error( "Split time before first 25m" )
        guessed_25m_split = 0
      if guessed_25m_split >= num_25m_splits:
        guessed_25m_split = num_25m_splits - 1
      if (guessed_25m_split & 1) == 0:
        any_splits_on_25m = True
      if splits[ guessed_25m_split ] is not None:
        logging.error( "More than one split in same 25m segment" )
      splits[ guessed_25m_split ] = Split( (guessed_25m_split + 1) * 25, split_time, False )
      
    # Now we fill in any missing splits with interpolated values
    final_split = Split( self.event.getDistance(), self.race_time, False )
    splits[ num_25m_splits - 1 ] = final_split
    previous_good_split = Split( 0, 0, False )
    for i in range( 0, num_25m_splits ):
      if splits[ i ] is None:
        # Find the next known split
        next_good_split = final_split
        for j in range( i + 1, num_25m_splits - 1 ):
          if splits[ j ] is not None:
            next_good_split = splits[j];
            break;
        # Interpolate
        this_split_distance = (i + 1) * 25;
        interp = (float(this_split_distance) - float(previous_good_split.distance)) / (float(next_good_split.distance) - float(previous_good_split.distance))
        splits[ i ] = Split( this_split_distance, previous_good_split.time + (interp * (next_good_split.time - previous_good_split.time)), True )
        #logging.info( "Interp: " + str( i ) + ", " + str( this_split_distance ) + ", " + str( interp ) + ", " + str( splits[ i ].time ) )
      else:
        previous_good_split = splits[i]
        
    # Now we can transfer the splits to self
    if any_splits_on_25m:
      self.splits = splits
    else:
      num_50m_splits = num_25m_splits / 2
      self.splits = [None] * num_50m_splits
      for i in range( 0, num_50m_splits ):
        self.splits[i] = splits[(i*2) + 1]
        #logging.info( str( self.splits[i] ) )
    
  # Internal helper that is called when a Swim has been read from the database.
  # This unpacks the data that is packed into the string, so they're available to read
  # as member variables.
  # Makes heavy use of string tokenising using split.
  def unpack_data(self):
    #logging.info( self.data )
    tokens = self.data.split( "|" )
    num_tokens = len( tokens )
    
    # Figure out what version data we have
    version = 0
    if tokens[0].startswith( "V" ):
      version = int( tokens[0][1:] )
      
    if version == 0:
      # Old version swim data, missing the version number
      self.asa_number = int( tokens[0] )
      self.event = Event( int( tokens[1] ) )
      self.date = helpers.ParseDate_dmY( tokens[2] )
      self.meet = tokens[3]
      self.asa_swim_id = -1
      if len( tokens[4] ) > 0:
        self.asa_swim_id = int( tokens[4] )
      # Ignore any splits data in version 0 because it's most likely nonsense
    else:
      # Version 1 or higher data.
      # Token 0 is the version number.
      self.asa_number = int( tokens[1] )
      self.event = Event( int( tokens[2] ) )
      self.date = helpers.ParseDate_dmY( tokens[3] )
      self.meet = tokens[4]
      self.asa_swim_id = int( tokens[5] )
      # Read the splits
      if tokens[6] == "-":
        # There are no splits available from the ASA for this swim
        self.splits = []
      else:
        split_times_from_asa = []
        splits = tokens[6].split( "," )
        if len(splits) > 1:
          #logging.info( "T:" + tokens[6] + "N: " + str( len(splits) ) )
          for split in splits:
            split_times_from_asa.append( float( split ) )
          self.fix_splits( split_times_from_asa )
    
    if version != 1:
      # Update database with latest version data
      logging.info( "Upgrading swim data to latest version" )
      self.repack_data()
      self.put()
    
  # Internal helper to re-pack self.data if we change something, like adding
  # splits for example.
  def repack_data(self):
    data_str = Swim.pack_data( self.asa_number, self.event, self.date, self.meet, self.asa_swim_id )
    if hasattr( self, 'splits' ):
      if len( self.splits ) == 0:
        # Write a "-" to mean there are no splits for this swim available.
        # This is to prevent us continually going to the ASA website for splits.
        data_str += "-"
      else:
        first = True
        for split in self.splits:
          if not split.interpolated:
            if not first:
              data_str += ","
            data_str += str( split.time )
            first = False
    self.data = data_str
    
  # Returns the asa number of the swimmer that this swim is for.
  def get_asa_swim_id(self):
    if self.asa_swim_id == -1:
      return None
    return self.asa_swim_id
    
  # Swim creation that takes a swimmer asa number and date-of-birth for cases where
  # we don't have a Swimmer (like when we're scraping a meet and we encounter a swimmer for
  # the first time, or one that needs upgrading from Cat 1)
  @classmethod
  def create(cls, asa_number, date_of_birth, event, date, meet, race_time, asa_swim_id = None):
    key = create_parent_key( asa_number, event )
    id = compute_swim_key_id( date, asa_number, event )

    age_on_day = helpers.CalcAge( date_of_birth, date )
    data = cls.pack_data( asa_number, event, date, meet, asa_swim_id )
    swim = cls( parent = key, id = id, age_on_day = age_on_day, race_time = race_time, data = data )
    swim.unpack_data()
    return swim
 
  # Retrieves a swimmer's PB for an event.
  # Optionally pass the age that you want the PB for.  This can be used to generate
  # club records by finding a swimmer's fastest 200 Free time when they were 11 for example.
  @classmethod
  def fetch_pb(cls, swimmer, event, aod = None ):
    key = create_parent_key( swimmer.asa_number, event )
    if aod is None:
      # We want this swimmer's absolute PB
      swims = cls.query( ancestor=key ).order(cls.race_time).fetch(1)
    else:
      # Fetch this swimmer's PB for the specified age
      swims = cls.query( Swim.age_on_day == aod, ancestor=key ).order(cls.race_time).fetch(1)
    if (swims is not None) and (len(swims) > 0):
      swims[0].unpack_data()
      return swims[0]
 
  # Retrieves all a swimmer's swims for an event.
  @classmethod
  def fetch_all(cls, asa_number, event ):
    key = create_parent_key( asa_number, event )
    swims = cls.query( ancestor=key ).order(cls.race_time).fetch()
    for swim in swims:
      swim.unpack_data()
    return swims

  # Convert to string, usually to send to the JS Swim constructor in swim.js
  def __str__(self):
    data_str = str( self.asa_number ) + "|" + str(self.event.to_int()) + "|" + self.date.strftime( "%d/%m/%Y" ) + "|" + self.meet + "|" + str( self.asa_swim_id ) + "|"
    if hasattr( self, 'splits' ):
      first = True
      previous_time = float(0)
      for split in self.splits:
        if not first:
          data_str += ","
        data_str += str( split.time - previous_time )
        if split.interpolated:
          data_str += "I"
        previous_time = split.time
        first = False
    data_str += "|" + str( self.race_time )
    data_str += "|" + self.create_swim_key_str()
    return data_str
