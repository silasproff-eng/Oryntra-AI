import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';


class SessionStore {
  static const _tokenKey = 'oryntra_session_token';
  static const _storage = FlutterSecureStorage();

  Future<String?> readToken() async {
    final secureToken = await _storage.read(key: _tokenKey);
    if (secureToken != null && secureToken.isNotEmpty) return secureToken;

    
    final prefs = await SharedPreferences.getInstance();
    final legacyToken = prefs.getString(_tokenKey);
    if (legacyToken != null && legacyToken.isNotEmpty) {
      await _storage.write(key: _tokenKey, value: legacyToken);
      await prefs.remove(_tokenKey);
      return legacyToken;
    }
    return null;
  }

  Future<void> saveToken(String token) async {
    await _storage.write(key: _tokenKey, value: token);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  Future<void> clear() async {
    await _storage.delete(key: _tokenKey);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }
}
