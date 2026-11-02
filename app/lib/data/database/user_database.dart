/// The user's own data: cars, diagnosis history, favourites and notes.
///
/// Deliberately a separate file from the diagnostic bundle. The bundle is replaced wholesale
/// on every database update; keeping user rows in it would delete them with it, and writing
/// to it would break the checksum the app verifies at launch.
library;

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

class UserDatabase {
  UserDatabase({required this.directory});

  static const int schemaVersion = 1;
  static const String fileName = 'autodoctor_user.sqlite';

  final String directory;
  Database? _database;

  Database get database {
    final Database? value = _database;
    if (value == null) {
      throw StateError('UserDatabase.open() has not completed');
    }
    return value;
  }

  String get path => p.join(directory, fileName);

  Future<Database> open() async {
    final Database existing = _database ?? await _openFile();
    _database = existing;
    return existing;
  }

  Future<Database> _openFile() async {
    return databaseFactory.openDatabase(
      path,
      options: OpenDatabaseOptions(
        version: schemaVersion,
        onCreate: (Database db, int version) async {
          await db.execute('''
            CREATE TABLE vehicles (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              nickname     TEXT,
              manufacturer TEXT,
              model        TEXT,
              model_year   INTEGER,
              engine       TEXT,
              fuel_type    TEXT,
              vin          TEXT,
              odometer_km  INTEGER,
              created_at   TEXT NOT NULL
            )
          ''');
          await db.execute('''
            CREATE TABLE diagnosis_records (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              vehicle_id   INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
              context_key  TEXT NOT NULL,
              code         TEXT NOT NULL,
              title_en     TEXT,
              status       TEXT NOT NULL DEFAULT 'open',
              note         TEXT,
              created_at   TEXT NOT NULL
            )
          ''');
          await db.execute('''
            CREATE TABLE favorites (
              context_key  TEXT PRIMARY KEY,
              code         TEXT NOT NULL,
              created_at   TEXT NOT NULL
            )
          ''');
          await db.execute('''
            CREATE TABLE notes (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              context_key  TEXT NOT NULL,
              body         TEXT NOT NULL,
              created_at   TEXT NOT NULL
            )
          ''');
          await db.execute(
            'CREATE INDEX idx_records_context ON diagnosis_records(context_key)',
          );
          await db.execute('CREATE INDEX idx_notes_context ON notes(context_key)');
        },
        onUpgrade: (Database db, int from, int to) async {
          // MIGRATIONS: add one block per version. Never edit an existing block - a device
          // that already ran it will not run it again.
          // if (from < 2) { ... }
        },
        onConfigure: (Database db) async {
          await db.execute('PRAGMA foreign_keys = ON');
        },
      ),
    );
  }

  Future<void> close() async {
    await _database?.close();
    _database = null;
  }
}
