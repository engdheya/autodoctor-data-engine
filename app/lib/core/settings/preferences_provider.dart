import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Overridden in `main()` with the resolved instance, and in tests with a mock.
/// Kept in its own file so the settings controller never imports the whole graph.
final Provider<SharedPreferences> sharedPreferencesProvider = Provider<SharedPreferences>(
  (Ref ref) => throw UnimplementedError('sharedPreferencesProvider must be overridden'),
);
