# todo-cli

A local command-line tool for managing personal todo lists. All data lives in
plain text files on your machine — nothing leaves your computer.

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

Note: cloud sync is explicitly out of scope and will not be added — if you need your tasks on multiple machines, use your own file-sync tooling.
