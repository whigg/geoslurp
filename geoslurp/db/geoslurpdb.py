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
# License along with geoslurp; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

# Author Roelof Rietbroek (roelof@geod.uni-bonn.de), 2019
from geoslurp.config.localsettings import readLocalSettings
from geoslurp.db.connector import GeoslurpConnector

def geoslurpConnect(args=None,readonlyuser=True,update=False):
    """Reads settings from configuration file and returns a database connection"""
    if args:
        userSettings=readLocalSettings(args=args,update=update,readonlyuser=readonlyuser)
    else:
        userSettings=readLocalSettings(update=update,readonlyuser=readonlyuser)

    return GeoslurpConnector(userSettings.host,userSettings.user,userSettings.password)
