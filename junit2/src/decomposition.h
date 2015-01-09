//////////////////////////////////////////////////////////////////
//
// Test logging facilities for SUSE test automation
//
// Copyright (C) 2015 Eric Bischoff <ebischoff@suse.de>
//
// This program is free software; you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation; either version 2 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program; if not, write to the Free Software
// Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
//
//////////////////////////////////////////////////////////////////

class QString;

class Decomposition
{
  private:
    int pairs;
    const char *keyBegin, *keyEnd,
               *nameBegin[10], *nameEnd[10],
               *valueBegin[10], *valueEnd[10];

  public:
    Decomposition();
    void parseDirective(const char *line);
    bool keyword(const char *value) const;
    QString getValue(const char *name, const char *defaultValue) const;
};
