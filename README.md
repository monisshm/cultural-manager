# Campus Culture — Cultural Event Management System

A responsive college cultural-fest website for organizing events and schedules, managing participant registrations and volunteer assignments, publishing announcements and competition results, and viewing registration reports.

## Features

- Sign in and create accounts as an organizer, participant, or volunteer.
- Admin, organizer, participant, and volunteer role-based access.
- Create, view, update, and delete cultural events.
- Set event categories, dates, venues, time slots, descriptions, and registration limits.
- Register for events, cancel a registration, and view registration status.
- Assign volunteers to events.
- Publish announcements and competition results.
- Review registration counts, capacity, and fill rates in reports.
- Store application data in a local SQLite database.
- Validate event rules and registration capacity using the Java event manager.

## Requirements

- Python 3.9 or later
- Flask
- JDK 11 or later, with `java` and `javac` available on your `PATH`

## Install and run

Open PowerShell in the project folder and run:

```powershell
py -m pip install Flask
javac -version
py app.py
```

If `py` is not available, use `python` instead:

```powershell
python -m pip install Flask
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser. The Java class is compiled automatically on the first Java-backed operation. Compiled class files are stored in the system temporary directory, not in the project source folder.

The SQLite database is created automatically as `cultural_fest.db` in the project folder when the app starts. Set the `CULTURAL_FEST_DATABASE` environment variable to use a different database path. The default development server uses port `5000`; set the `PORT` environment variable to choose another port.

## Demo sign-in accounts

| Role | Username / ID | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Organizer | `organizer` | `organizer123` |
| Participant | `participant` | `participant123` |
| Volunteer | `volunteer` | `volunteer123` |

These are development demo credentials. Change or remove the default accounts before using the app in a shared or production environment. Users can also create organizer, participant, and volunteer accounts through the sign-up form; admin accounts are not self-service.

## Project files

| File | Purpose |
|---|---|
| `index.html` | Application structure and pages |
| `style.css` | Responsive visual styling |
| `script.js` | Frontend navigation, validation, rendering, and API requests |
| `app.py` | Flask server, API, authentication, authorization, and SQLite operations |
| `EventManager.java` | Java event, registration, capacity, and volunteer-assignment validation |

