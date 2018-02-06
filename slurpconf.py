# This file is part of geoslurp.
# geoslurp is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

# geoslurp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with Frommle; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

# Author Roelof Rietbroek (roelof@geod.uni-bonn.de), 2018

#note assumes Python > 3.4
from pathlib import Path
import yaml

class slurpconf():
    """ Class which reads and writes configure data in yaml format"""
    def __init__(self):
        self.confyaml=Path.home()/'.geoslurp.yaml'
        if Path.exists(self.confyaml):
            #Read parameters from yaml file
            fid=open(self.confyaml,'r')
            self.confobj=[x for x in yaml.safe_load_all(fid)][0]
            fid.close()
    def writeDefaultConfig(self):
        """Write the default configuration to ${HOME}/.geoslurp.yaml.default"""
        obj={"Mongo":"localhost:27017","DataDir":"/tmp/geoslurp"}
        fid=open(str(self.confyaml)+'.default','w')
        fid.write("# Default configuration file for geoslurp\n")
        fid.write("# Change settings below and save file to .geoslurp.yaml\n")
        yaml.dump(obj,fid,default_flow_style=False)
        fid.close()

    def write(self):
        """Writes changed setup back to confuguration file"""
        fid=open(self.confyaml,'w')
        yaml.dump(self.confobj,fid,default_flow_style=False)
        fid.close()

    #The operators below overload the [] operators allowing the retrieval and  setting of dictionary items
    def __getitem__(self,arg):
        return self.confobj[arg]

    def __setitem__(self,key,val):
        self.confobj[key]=val

