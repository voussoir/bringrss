BringRSS
========

It brings you the news.

Live demo: https://bringrss.voussoir.net

## What am I looking at

BringRSS is an RSS client / newsreader made with Python, SQLite3, and Flask. Its main features are:

- Automatic feed refresh with separate intervals per feed.
- Feeds arranged in hierarchical folders.
- Filters for categorizing or removing news based on your criteria.
- Sends news objects to your own Python scripts for arbitrary post-processing, emailing, downloading, etc.
- Embeds videos from YouTube feeds.
- News text is filtered by [DOMPurify](https://github.com/cure53/DOMPurify) before display.
- Supports multiple enclosures.

Because BringRSS runs a webserver, you can access it from every device in your house via your computer's LAN IP. BringRSS provides no login or authentication, but if you have a reverse proxy handle that for you, you could run BringRSS on an internet-connected machine and access your feeds anywhere.

## Screenshots

![](https://user-images.githubusercontent.com/7299570/160224740-734f0517-1b03-48e1-80a6-b96129d7d7fc.png)

![](https://user-images.githubusercontent.com/7299570/160224741-398da5aa-af92-42e3-a921-118cc6e54a68.png)

![](https://user-images.githubusercontent.com/7299570/160224742-f482b8dd-59cd-4a8a-b70f-67c1e9250e83.png)

![](https://user-images.githubusercontent.com/7299570/160224743-9f287446-2f1f-4465-8c23-f8d2591fe5e0.png)

![](https://user-images.githubusercontent.com/7299570/160224744-e43d8838-74a4-4a06-b304-10e5102614fc.png)

![](https://user-images.githubusercontent.com/7299570/160224745-479bd9c5-9c42-4514-8a49-42df972ec978.png)

![](https://user-images.githubusercontent.com/7299570/160224748-f73e7db7-1664-47ce-a391-86f947fd6c84.png)

![](https://user-images.githubusercontent.com/7299570/160224750-10aa322e-8036-4410-8415-9fdbb9e8da99.png)

## Setting up

As you'll see below, BringRSS has a core backend package and separate frontends that use it. These frontend applications will use `import bringrss` to access the backend code. Therefore, the `bringrss` package needs to be in the right place for Python to find it for `import`.

1. Run `pip install -r requirements.txt --upgrade` after reading the file and deciding you are ok with the dependencies.

2. Make a new folder somewhere on your computer, and add this folder to your `PYTHONPATH` environment variable. For example, I might use `D:\pythonpath` or `~/pythonpath`. Close and re-open your Command Prompt / Terminal so it reloads the environment variables.

3. Add a symlink to the bringrss folder into that folder:

    The repository you are looking at now is `D:\Git\BringRSS` or `~/Git/BringRSS`. You can see the folder called `bringrss`.

    Windows: `mklink /d fakepath realpath`  
    for example `mklink /d "D:\pythonpath\bringrss" "D:\Git\BringRSS\bringrss"`

    Linux: `ln --symbolic realpath fakepath`  
    for example `ln --symbolic "~/Git/BringRSS/bringrss" "~/pythonpath/bringrss"`

4. Run `python -c "import bringrss; print(bringrss)"`. You should see the module print successfully.

## Running BringRSS CLI

BringRSS offers a commandline interface so you can use cronjobs to refresh your feeds. More commands may be added in the future.

1. `cd` to the folder where you'd like to create the BringRSS database.

2. Run `python frontends/bringrss_cli.py --help` to learn about the available commands.

3. Run `python frontends/bringrss_cli.py init` to create a database in the current directory.

Note: Do not `cd` into the frontends folder. Stay in the folder that contains your `_bringrss` database and specify the full path of the frontend launcher. For example:

    Windows:
    D:\somewhere> python D:\Git\BringRSS\frontends\bringrss_cli.py

    Linux:
    /somewhere $ python /Git/BringRSS/frontends/bringrss_cli.py

It is expected that you create a shortcut file or launch script so you don't have to type the whole filepath every time. For example, I have a `bringcli.lnk` on my PATH with `target=D:\Git\BringRSS\frontends\bringrss_cli.py`.

## Running BringRSS Flask locally

1. Run `python frontends/bringrss_flask/bringrss_flask_dev.py --help` to learn the available options.

2. Run `python frontends/bringrss_flask/bringrss_flask_dev.py [port]` to launch the flask server. If this is your first time running it, you can add `--init` to create a new database in the current directory. Port defaults to 27464 if not provided.

3. Open your web browser to `localhost:<port>`.

Note: Do not `cd` into the frontends folder. Stay in the folder that contains your `_bringrss` database and specify the full path of the frontend launcher. For example:

    Windows:
    D:\somewhere> python D:\Git\BringRSS\frontends\bringrss_flask\bringrss_flask_dev.py 5001

    Linux:
    /somewhere $ python /Git/BringRSS/frontends/bringrss_flask/bringrss_flask_dev.py 5001

Add `--help` to learn the arguments.

It is expected that you create a shortcut file or launch script so you don't have to type the whole filepath every time. For example, I have a `bringflask.lnk` on my PATH with `target=D:\Git\BringRSS\frontends\bringrss_flask\bringrss_flask_dev.py`.

## Running BringRSS Flask with Gunicorn

BringRSS provides no authentication whatsoever, so you probably shouldn't deploy it publicly unless your proxy server does authentication for you. However, I will tell you that for the purposes of running the demo site, I am using a script like this:

    export BRINGRSS_DEMO_MODE=1
    ~/cmd/python ~/cmd/gunicorn_py bringrss_flask_prod:site --bind "0.0.0.0:PORTNUMBER" --worker-class gevent --access-logfile "-" --access-logformat "%(h)s | %(t)s | %(r)s | %(s)s %(b)s"

## Running BringRSS REPL

The REPL is a great way to test a quick idea and learn the data model.

1. Use `bringrss_cli init` to create the database in the desired directory.

2. Run `python frontends/bringrss_repl.py` to launch the Python interpreter with the BringDB pre-loaded into a variable called `B`. Try things like `B.get_feed` or `B.get_newss`.

Note: Do not `cd` into the frontends folder. Stay in the folder that contains your `_bringrss` database and specify the full path of the frontend launcher. For example:

    Windows:
    D:\somewhere> python D:\Git\BringRSS\frontends\bringrss_repl.py

    Linux:
    /somewhere $ python /Git/BringRSS/frontends/bringrss_repl.py

It is expected that you create a shortcut file or launch script so you don't have to type the whole filepath every time. For example, I have a `bringrepl.lnk` on my PATH with `target=D:\Git\BringRSS\frontends\bringrss_repl.py`.

## Help wanted: javascript perf & layout thrashing

I think there is room for improvement in [root.html](https://github.com/voussoir/bringrss/blob/master/frontends/bringrss_flask/templates/root.html)'s javascript. When reading a feed with a few thousand news items, the UI starts to get slow at every interaction:

- After clicking on a news, it takes a few ms before it turns selected.
- The newsreader takes a few ms to populate with the title even though it's pulled from the news's DOM, not the network.
- After receiving the news list from the server, news are inserted into the dom in batches, and each batch causes the UI to stutter if you are also trying to scroll or click on things.

If you have any tips for improving the performance and responsiveness of the UI click handlers and reducing the amount of reflow / layout caused by the loading of news items or changing their class (selecting, reading, recycling), I would appreciate you getting in touch at contact@voussoir.net or opening an issue. Please don't open a pull request without talking to me first.

I am aware of virtual scrolling techniques where DOM rows don't actually exist until you scroll to where they would be, but this has the drawback of breaking ctrl+f and also it is hard to precompute the scroll height since news have variable length titles. I would prefer simple fixes like adding CSS rules that help the layout engine make better reflow decisions.

## To do list

- Maybe we could add a very basic password system to facilitate running an internet-connected instance. No user profiles, just a single password to access the whole system. I did this with [simpleserver](https://github.com/voussoir/else/blob/master/SimpleServer/simpleserver.py).
- "Fill in the gaps" feature. Many websites have feeds that don't reach back all the way to their first post. When discovering a new blog or podcast, catching up on their prior work requires manual bookmarking outside of your newsreader. It would be nice to dump a list of article URLs into BringRSS and have it generate news objects as if they really came from the feed. Basic information like url, title, and fetched page text would be good enough; auto-detecting media as enclosures would be better. Other attributes don't need to be comprehensive. Then you could have everything in your newsreader.

## Mirrors

https://git.voussoir.net/voussoir/bringrss

https://github.com/voussoir/bringrss

https://gitlab.com/voussoir/bringrss

https://codeberg.com/voussoir/bringrss
