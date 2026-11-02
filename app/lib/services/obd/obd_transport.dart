/// Contract for a future OBD-II adapter (ELM327 over Bluetooth Classic or BLE).
///
/// No implementation ships in this build and no command is sent to a vehicle. The interface
/// exists so the transport can be added without touching the database or the UI.
library;

class ObdDevice {
  const ObdDevice({required this.name, required this.address, required this.isBle});

  final String name;
  final String address;
  final bool isBle;
}

class LiveSample {
  const LiveSample({required this.pid, required this.raw, required this.measuredAt});

  final String pid;
  final String raw;
  final DateTime measuredAt;
}

abstract class ObdTransport {
  Future<ObdDevice> findDevice();

  Future<void> connect(ObdDevice device);

  Future<void> disconnect();

  /// Codes currently stored by the ECU, as reported by the adapter.
  Future<List<String>> readStoredCodes();

  Future<List<String>> readPendingCodes();

  Future<List<LiveSample>> readLiveData(List<String> pids);

  Future<Map<String, Object?>> readFreezeFrame(String code);

  /// Clearing codes is destructive and stays disabled until an explicit user confirmation
  /// and a qualified-technician review exist. Phase 1 never calls this.
  Future<void> clearCodes();
}
