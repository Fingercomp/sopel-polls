import pymongo
from pymongo import MongoClient

import re
import datetime
import math

from sopel.module import commands

yes_answers = ["on", "yes", "+", "yep", "yup", "yeah"]
no_answers = ["off", "no", "nope", "nop", "no way", "nein"]


class Poll:

    # XXX: Mongo database URL
    url = "mongodb://localhost:15460"

    # XXX: list of admins (they have access to admin commands)
    admins = ["Totoro", "fingercomp", "LeshaInc"]

    partial = {}

    codename = re.compile("^[A-Za-z0-9_.-]{3,30}$")
    option = re.compile("^\S.*$")

    def __init__(self):
        self.client = MongoClient(self.url)
        self.db = self.client.brote.poll
        self.db.create_index([("name", pymongo.ASCENDING)])

        self.updates()

    def __del__(self):
        self.client.close()

    def updates(self):
        # Added "anonymous" polls
        self.db.find_one_and_update({
            "anonymous": {
                "$exists": False
            }
        }, {"$set": {"anonymous": False}})

        # Renamed field to more sensible name
        self.db.find_one_and_update({
            "public": {"$exists": True}
        }, {"$rename": {"public": "interim"}})

    def new_poll(self, author, name, title, options, date, interim, anonymous):
        poll = {"author": author,
                "name": name,
                "title": title,
                "options": options,
                "date": date,
                "open": False,
                "interim": interim,
                "anonymous": anonymous}
        self.db.insert_one(poll)

    def get_poll(self, name):
        return self.db.find_one({"name": name})

    def del_poll(self, name):
        return self.db.delete_one({"name": name}).deleted_count

    def open(self, name):
        self.db.find_one_and_update({"name": name}, {
            "$set": {"open": True}
        })

    def close(self, name):
        self.db.find_one_and_update({"name": name}, {
            "$set": {"open": False}
        })

    def add_vote(self, user, index, name):
        poll = self.get_poll(name)
        if not poll:
            return "no such poll"
        if not poll["open"]:
            return "poll is closed"
        opt = [x for x in filter(
            lambda item: item["index"] == index,
            poll["options"]
        )]
        if len(opt) == 0:
            return "no such index"
        opt = opt[0]
        if user in opt["votes"]:
            return "already voted"
        self.db.find_one_and_update(
            {"name": name,
             "options.index": index},
            {"$push": {"options.$.votes": user}}
        )
        return True

    def del_vote(self, user, index, name):
        poll = self.get_poll(name)
        if not poll:
            return "no such poll"
        if not poll["open"]:
            return "poll is closed"
        opt = [x for x in filter(
            lambda item: item["index"] == index,
            poll["options"]
        )]
        if len(opt) == 0:
            return "no such index"
        opt = opt[0]
        if user not in opt["votes"]:
            return "haven't voted"
        self.db.find_one_and_update(
            {"name": name,
             "options.index": index},
            {"$pull": {"options.$.votes": user}}
        )
        return True

    def vote(self, user, index, name):
        poll = self.get_poll(name)
        if not poll:
            return "no such poll"
        if not poll["open"]:
            return "poll is closed"
        for opt in poll["options"]:
            if opt["index"] == index:
                break
        else:
            return "no such index"
        already_voted = [x for x in filter(
            lambda item: user in item["votes"],
            poll["options"]
        )]
        if len(already_voted) > 0:
            self.del_vote(user, already_voted[0]["index"], name)
        self.add_vote(user, index, name)
        return True

    def isReady(self, part_poll):
        if (part_poll["name"] and
                part_poll["title"] and
                part_poll["interim"] is not None and
                part_poll["options"] and
                len([x for x in part_poll["options"]]) > 1):
            return True
        return False

    def checkAccess(self, poll, trigger):
        return (poll["author"] == trigger.nick or
                trigger.nick in self.admins)


self = Poll()


def bar(width, perc):
    chars = [""]
    for i in range(0x258f, 0x2587, -1):
        chars.append(chr(i))
    cell_width = width / 100
    w = perc * cell_width
    blocks = math.floor(w)
    fr = w - math.floor(w)
    idx = math.floor(fr * 8)
    if idx == 8:
        idx = 7
    last_block = chars[idx]
    empty_blocks = width - blocks - len(last_block)
    if perc < 25:
        color = "05"
    elif perc < 50:
        color = "07"
    elif perc < 66:
        color = "08"
    elif perc < 85:
        color = "09"
    elif perc < 100:
        color = "10"
    else:
        color = "11"
    return ("\x0301▕\x03" +
            "\x03" + color +
            "█" * blocks +
            last_block +
            " " * empty_blocks +
            "\x0301▏\x03")


@commands("poll")
def poll(bot, trigger):
    try:
        cmd = trigger.group(2).split(" ")[0]
    except (AttributeError, IndexError):
        cmd = None
    if not cmd:
        return False
    else:
        arg = trigger.group(2)[len(cmd) + 1:]
    if trigger.nick not in self.partial:
        if cmd == "create":
            self.partial[trigger.nick] = {
                "name": None,
                "title": None,
                "date": None,
                "options": None,
                "interim": None,
                "settings": {"anonymous": False}
            }
            bot.reply("\x02SWITCHED TO EDIT MODE\x02. "
                      "Let's create a new poll!")
            bot.reply("Type \x1d.poll help\x1d for the list of commands")
            return True
        elif cmd == "help":
            bot.reply("\x1d.poll create\x1d: create a poll, and switch "
                      "to edit mode.")
            bot.reply("\x1d.poll delete <poll>\x1d: delete a poll.")
            bot.reply("\x1d.poll info <poll>\x1d: show detailed report about "
                      "poll.")
            bot.reply("\x1d.poll vote <poll> <vote index>\x1d: vote. Note "
                      "that an index is expected (see .poll info), not "
                      "the full name of an option.")
            bot.reply("\x1d.poll open <poll>\x1d: open a poll.")
            bot.reply("\x1d.poll close <poll>\x1d: close a poll.")
            bot.reply("\x1d.poll list\x1d: List polls.")
            bot.reply("\x1d.poll unvote <poll>\x1d: Remove your vote.")
            bot.reply("\x1d.poll delvote <poll> <user>\x1d: Remove vote of a "
                      "user. Only available for admins.")
            return True
    else:
        # EDIT MODE
        poll = self.partial[trigger.nick]
        if cmd == "#":
            if not self.codename.match(arg):
                bot.reply("Bad codename. It's length must be greater than "
                          "2 and less than 31, and it must contain "
                          "alphanumeric symbols, underline, period, or dash.")
                return
            if self.get_poll(arg):
                bot.reply("Codename must be unique.")
                return
            poll["name"] = arg
            bot.reply("The \x02codename\x02 set to '" + arg + "'!")
            return True
        elif cmd == "!":
            poll["title"] = arg
            bot.reply("The \x02title\x02 set to '" + arg + "\x0f'!")
            return True
        elif cmd == "@":
            if arg.lower() in yes_answers:
                poll["interim"] = True
                bot.reply("Interim results are set to be \x02available\x02!")
                return True
            elif arg.lower() in no_answers:
                poll["interim"] = False
                bot.reply("Results will be \x02unavaiable\x02 until closed!")
                return True
            else:
                bot.reply("Erm, what?")
                return
        elif cmd == "?":
            bot.reply("\x02Codename:\x02 " +
                      ("'" + poll["name"] + "'"
                       if poll["name"] else "not set"))
            bot.reply("\x02Title:\x02 " +
                      ("'" + poll["title"] + "'"
                       if poll["title"] else "not set"))
            if poll["interim"] is None:
                bot.reply("\x02Votes:\x02 not set")
            else:
                bot.reply("\x02Interim results:\x02 " +
                          ("yes" if poll["interim"] else "no"))
            if poll["options"]:
                bot.reply("\x02Options:\x02 " + ", ".join(
                    "\x02#" + str(pos) + "\x02: " + name + "\x0f"
                    for pos, name in enumerate(poll["options"])
                ))
            else:
                bot.reply("\x02Options:\x02 not set")
            bot.reply("The poll is \x02anonymous\x02."
                      if poll["settings"]["anonymous"] else
                      "The poll is \x02unanonymous\x02.")
            if self.isReady(poll):
                bot.reply("Poll is \x02ready\x02 to be commited.")
            else:
                bot.reply("Some fields are still \x02unset\x02.")
            return True
        elif cmd == ">":
            if not self.option.match(arg):
                bot.reply("Well, you didn't provide a name for your "
                          "option.")
                return
            if poll["options"] is None:
                poll["options"] = []
            poll["options"].append(arg)
            bot.reply("Added option #" + str(poll["options"].index(arg)) +
                      ": '" + arg + "\x0f'")
            return True
        elif cmd == "<":
            try:
                index = int(arg)
            except ValueError:
                bot.reply("Bad argument. You're probably providing a "
                          "name. Well, I need an index.")
                return
            if poll["options"] is None:
                bot.reply("You'd better add an option before using this "
                          "command :)")
                return
            try:
                poll["options"][index]
            except IndexError:
                bot.reply("No such index.")
                return
            opt = poll["options"].pop(index)
            if len(poll["options"]) == 0:
                poll["options"] = None
            bot.reply("Removed option #" + str(index) + ": '" + opt + "\x0f'")
            return True
        elif cmd == "=":
            try:
                set_name, set_arg = arg.split(" ", 1)
            except ValueError:
                set_name = arg
                set_arg = ""
            if set_name in ["anon", "anonymous"]:
                if set_arg in yes_answers:
                    poll["settings"]["anonymous"] = True
                    bot.reply("Okay, votes \x02won't\x02 be ever shown.")
                    return True
                elif set_arg in no_answers:
                    poll["settings"]["anonymous"] = False
                    bot.reply("Well, I've marked your poll as unanonymous.")
                    return True
                else:
                    bot.reply("Uh oh, I couldn't understand what you told me.")
                    return
            else:
                bot.reply("I'm afraid I can't decipher what you gave :<")
                return
        elif cmd == "~~~":
            if not self.isReady(poll):
                bot.reply("Some fields are still unset. You can't commit "
                          "partially filled polls.")
                return
            options = [{"index": pos, "name": name, "votes": []}
                       for pos, name in enumerate(poll["options"])]
            date = datetime.datetime.utcnow()
            self.new_poll(author=trigger.nick,
                          name=poll["name"],
                          title=poll["title"],
                          date=date,
                          options=options,
                          interim=poll["interim"],
                          anonymous=poll["settings"]["anonymous"])
            self.partial.pop(trigger.nick)
            bot.reply("Your poll is created. When you're ready, open it.")
            bot.reply("\x02SWITCHED TO NORMAL MODE\x02.")
            return True
        elif cmd == "***":
            self.partial.pop(trigger.nick)
            bot.reply("Your poll is deleted. \x02SWITCHED TO NORMAL MODE\x02.")
            return True
        elif cmd == "help":
            if arg == "=":
                bot.reply("\x1d.poll = anon <{yes|no}>\x1d: set whether the "
                          "poll should be anonymous (won't list nicks of "
                          "voters).")
                return True
            bot.reply("\x1d.poll # <code name>\x1d: set the code name. It "
                      "must only contain alphanumeric characters, underline, "
                      "dash, or period. Its length must be greater than 2 and "
                      "less than 31.")
            bot.reply("\x1d.poll ! <title>\x1d: set the title.")
            bot.reply("\x1d.poll @ <{on|off}>\x1d: when 'on', votes are shown "
                      "even if the poll is open.")
            bot.reply("\x1d.poll > <option name>\x1d: append an option.")
            bot.reply("\x1d.poll < <option index>\x1d: remove an option. Note "
                      "that an index is expected (see .poll ?), not the full "
                      "name of an option.")
            bot.reply("\x1d.poll ?\x1d: show pending changes.")
            bot.reply("\x1d.poll = <setting> [value]\x1d: set some "
                      "optional settings. See \x1d.poll help =\x1d")
            bot.reply("\x1d.poll ~~~\x1d: commit changes.")
            bot.reply("\x1d.poll ***\x1d: abort changes.")
            return True

    if cmd in ["close", "open"]:
        poll = self.get_poll(arg)
        if not poll:
            bot.reply("Erm, no such poll.")
            return
        if not self.checkAccess(poll, trigger):
            bot.reply("Erm, no access.")
            return
        if cmd == "open":
            self.open(arg)
            bot.reply("Poll opened!")
        else:
            self.close(arg)
            bot.reply("Poll closed!")
    elif cmd == "vote":
        if len(arg.split(" ")) != 2:
            bot.reply("Something is wrong with your command. Type "
                      "\x1d.poll help\x1d for help.")
            return
        poll_name, index = arg.split(" ")
        try:
            index = int(index)
        except ValueError:
            bot.reply("Bad index. Yes, I need an index, not name!")
            return
        result = self.vote(user=trigger.nick,
                           index=index,
                           name=poll_name)
        if result is True:
            poll = self.get_poll(poll_name)
            for opt in poll["options"]:
                if opt["index"] == index:
                    name = opt["name"]
                    break
            bot.reply("You've voted for \x02#" + str(index) + "\x02: " +
                      name + "\x0f!")
            return True
        else:
            bot.reply("Uh oh, " + result + ".")
            return
    elif cmd in ["delete", "remove"]:
        poll = self.get_poll(arg)
        if not poll:
            bot.reply("Erm, no such poll.")
            return
        if not self.checkAccess(poll, trigger):
            bot.reply("Erm, no access.")
            return
        if poll["open"]:
            bot.reply("Close the poll first!")
            return
        else:
            self.del_poll(arg)
            bot.reply("Poll has been deleted.")
            return True
    elif cmd == "info":
        poll = self.get_poll(arg)
        if not poll:
            bot.reply("Uh oh, no such poll.")
            return
        bot.reply("\x02Title:\x02 " + poll["title"])
        bot.reply("\x02Created by\x02 " + poll["author"] + " at " +
                  str(poll["date"]))
        if poll["open"] and not poll["interim"]:
            total = 0
            maxLen = 0
            for item in poll["options"]:
                total += len(item["votes"])
                maxLen = max(maxLen, len(item["name"]))
            bot.reply("\x02" + str(total) + "\x02 votes total.")
            for item in poll["options"]:
                bot.reply("  \x02#" + str(item["index"]) + "\x02: " +
                          item["name"])
        else:
            total = 0
            maxLen = 0
            for item in poll["options"]:
                total += len(item["votes"])
                maxLen = max(maxLen, len(item["name"]))
            bot.reply("\x02" + str(total) + "\x02 votes total.")
            for item in poll["options"]:
                vnum = len(item["votes"])
                if total == 0:
                    perc = 0
                else:
                    perc = round(100 * vnum / total, 1)
                bot.reply("  \x02" + str(vnum) + "\x02 votes " +
                          "{:>5}".format(perc) + "% " +
                          bar(10, perc) + " \x02#" +
                          str(item["index"]) + "\x02: " +
                          "{:<{len}}".format(item["name"] + "\x0f",
                                             len=maxLen + 1) +
                          (" │ " + ", ".join(item["votes"])
                           if not poll["anonymous"] else ""))
        return True
    elif cmd == "list":
        if self.db.count() == 0:
            bot.reply("No polls.")
            return True
        polls = [x for x in self.db.find()]
        bot.reply("Polls: " + ", ".join(
            ("\x02" if i["open"] else "\x0301") + i["name"] + "\x0f"
            for i in polls
        ))
        return True
    elif cmd == "unvote":
        poll = self.get_poll(arg)
        if not poll:
            bot.reply("Erm, no such poll.")
            return
        for option in poll["options"]:
            if trigger.nick in option["votes"]:
                index = option["index"]
                break
        else:
            bot.reply("Wait, don't you think you need to vote first?")
        result = self.del_vote(trigger.nick, index, arg)
        if result is True:
            bot.reply("All set! Your vote has been deleted.")
            return True
        else:
            bot.reply("Uh oh, " + result + ".")
            return
    elif cmd in ["delvote", "remvote"]:
        if trigger.nick not in self.admins:
            bot.reply("I'm sorry, you don't have permission to run this "
                      "command.")
            return
        if len(arg.split(" ")) != 2:
            bot.reply("Something is wrong with your command. Type "
                      "\x1d.poll help\x1d for help.")
            return
        poll_name, user = arg.split(" ")
        poll = self.get_poll(poll_name)
        if not poll:
            bot.reply("Erm, no such poll.")
            return
        for option in poll["options"]:
            if user in option["votes"]:
                index = option["index"]
                break
        else:
            bot.reply("The user haven't even voted for any of the "
                      "options!")
            return
        result = self.del_vote(user, index, poll_name)
        if result is True:
            bot.reply("Well, their vote has been deleted.")
            return True
        else:
            bot.reply("Uh oh, " + result + ".")
            return
    else:
        bot.reply("Unknown command.")
        return
