import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class QuantLabStore {
  static const _storageKey = 'oryntra_quant_lab_reports_v1';
  static const _maxReports = 12;

  Future<List<Map<String, dynamic>>> readAll() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_storageKey);
    if (raw == null || raw.isEmpty) return const [];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return const [];
      return decoded
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  Future<List<Map<String, dynamic>>> save({
    required Map<String, dynamic> report,
    required List<String> tickers,
  }) async {
    final existing = await readAll();
    final fingerprint = report['dataset_fingerprint']?.toString() ?? '';
    final id = fingerprint.isNotEmpty
        ? fingerprint
        : DateTime.now().microsecondsSinceEpoch.toString();
    final entry = <String, dynamic>{
      'id': id,
      'saved_at': DateTime.now().toUtc().toIso8601String(),
      'tickers': tickers,
      'model': report['configuration'] is Map
          ? report['configuration']['model']?.toString()
          : null,
      'fingerprint': fingerprint,
      'report': report,
    };
    final updated = [
      entry,
      ...existing.where((item) => item['id']?.toString() != id),
    ].take(_maxReports).toList();
    await _write(updated);
    return updated;
  }

  Future<List<Map<String, dynamic>>> delete(String id) async {
    final updated = (await readAll())
        .where((item) => item['id']?.toString() != id)
        .toList();
    await _write(updated);
    return updated;
  }

  Future<void> _write(List<Map<String, dynamic>> entries) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_storageKey, jsonEncode(entries));
  }
}
