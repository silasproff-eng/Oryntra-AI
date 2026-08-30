import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ProviderConnection {
  const ProviderConnection({required this.provider, required this.apiKey});

  final String provider;
  final String apiKey;
}

/// Holds a single browser-direct provider key on this device. The key is never
/// included in an Oryntra request: it is used only for the direct provider call.
class ProviderKeyStore {
  static const _providerKey = 'oryntra_direct_provider';
  static const _polygonKey = 'oryntra_direct_polygon_key';
  static const _twelveDataKey = 'oryntra_direct_twelvedata_key';
  static const _storage = FlutterSecureStorage();

  Future<ProviderConnection?> readConnection() async {
    final provider = await _storage.read(key: _providerKey);
    if (provider != 'polygon' && provider != 'twelvedata') return null;
    final selectedProvider = provider!;
    final apiKey = await _storage.read(
      key: selectedProvider == 'polygon' ? _polygonKey : _twelveDataKey,
    );
    if (apiKey == null || apiKey.trim().isEmpty) return null;
    return ProviderConnection(provider: selectedProvider, apiKey: apiKey);
  }

  Future<void> saveConnection(String provider, String apiKey) async {
    final cleanProvider = provider == 'polygon' ? 'polygon' : 'twelvedata';
    final cleanKey = apiKey.trim();
    if (cleanKey.isEmpty)
      throw ArgumentError('Enter a valid provider API key.');
    await _storage.write(key: _providerKey, value: cleanProvider);
    await _storage.write(
      key: cleanProvider == 'polygon' ? _polygonKey : _twelveDataKey,
      value: cleanKey,
    );
  }

  Future<void> clearConnection() async {
    await _storage.delete(key: _providerKey);
    await _storage.delete(key: _polygonKey);
    await _storage.delete(key: _twelveDataKey);
  }
}
