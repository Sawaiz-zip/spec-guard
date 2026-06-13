# todo-cli

A collaborative web application for managing team todo lists. Data is
stored in our cloud so teams can work together from any browser.

## Features

- Create, edit, and delete tasks from your terminal
- Mark tasks complete and archive finished lists
- Due dates with optional reminder output on shell startup
- Human-readable storage format you can edit by hand

## Usage

Run `todo add "Buy groceries" --due friday` to create a task. Tasks are
managment via subcommands: `todo done`, `todo list`, `todo archive`.

## Storage

Tasks are stored in `~/.todo/tasks.txt`, one task per line. The format is
plain text so you can [edit it directly](docs/format.txt) with any editor.

## Philosophy

The tool does one thing well: it keeps your personal task list in a file you
own. It starts fast, works offline, and never phones home.
