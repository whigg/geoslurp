# This file is part of geoslurp
# geoslurp-tools is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

# geoslurp-tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with geoslurp; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

# Author Roelof Rietbroek (roelof@geod.uni-bonn.de), 2020

import os
import geopandas as gpd
import pandas as pd
from geoslurp.tools.shapelytools import shpextract
from geoslurp.db.settings import MirrorMap
import re
import tarfile
def exportGeoQuery(qryresult,outputfile,layer=None,driver="GPKG",packFiles=False,striproot=None):
    """Export the results of a query to a (portable output file, e.g. a geopackage and possibly a filearchive)"""
    if not "geom" in qryresult.keys():
        raise RunTimeError("no geometry found in the specified query")

    df = gpd.GeoDataFrame()
    df["geometry"]=None
    
    #specify columns
    for ky in (ky for ky in qryresult.keys() if ky not in ["geom","id"]):
        df[ky]=None
   
    if packFiles:
        #open a tgz archive
        farchive=os.path.splitext(outputfile)[0]+"_files.tgz"
        if striproot:
            mmap=MirrorMap(striproot,farchive+":/")

        #open/reopen archive 
        tarar=tarfile.open(farchive,mode='w:gz')

    else:
        tarar=None

    #add new rows
    for entry in qryresult:
        entrymod={}
        for ky,val in entry.items():
            if ky == "geom":
                val=shpextract(entry)
                ky="geometry"
            elif ky == "id":
                val=None
            elif ky == "uri" and packFiles:
                #modify the uri and add file in the archive
                if not striproot:
                    #try stripping of everything before and including 'geoslurp' from the path
                    striproot=re.search("^.*/geoslurp/",val).group(0)
                    mmap=MirrorMap(striproot,farchive+":/")
                uriorig=val
                val=mmap.apply(val)
                #create a new tarfile member if needed
                try:
                    basef=mmap.strip(uriorig)
                    tinfo=tarar.getmember(basef)
                except KeyError:
                    #create a new member
                    tarar.add(name=uriorig,arcname=basef)
            if val:
                entrymod[ky]=val

        df=df.append(entrymod,ignore_index=True)
    
    if packFiles:
        tarar.close()
    #export to file
    df.to_file(outputfile, layer=layer, driver=driver)



def exportQuery(qryresult,outputfile,layer=None,packFiles=False,driver="SQL"):
    """Export a query without a geometry column, and possibly pack corresponding files"""
    
    
    pass


def exportGeoTable(table,outfile,addFiles=False):
    """Export a entire table with a geometry column""" 
    raise NotImplementedError("This functionality is currently not implemented")


def exportTable(table,outfile,addFiles=False):
    """Export a entire table without a geometry column""" 
    raise NotImplementedError("This functionality is currently not implemented")

