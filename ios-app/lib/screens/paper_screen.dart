import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../widgets/adaptive_banner.dart';
import '../widgets/common.dart';

class PaperScreen extends StatefulWidget {
  const PaperScreen({
    super.key,
    required this.api,
    required this.signedIn,
    required this.onCreateAccount,
  });

  final ApiService api;
  final bool signedIn;
  final VoidCallback onCreateAccount;

  @override
  State<PaperScreen> createState() => PaperScreenState();
}

class PaperScreenState extends State<PaperScreen> {
  List<dynamic> _trades = const [];
  bool _loading = false;
  String? _error;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    if (widget.signedIn) _load();
  }

  @override
  void didUpdateWidget(covariant PaperScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.signedIn && widget.signedIn) {
      _load();
    } else if (oldWidget.signedIn && !widget.signedIn) {
      setState(() => _trades = const []);
    }
  }

  Future<void> _load() async {
    final generation = ++_loadGeneration;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final trades = await widget.api.paperTrades();
      if (!mounted || generation != _loadGeneration) return;
      setState(() => _trades = trades);
    } catch (_) {
      if (!mounted || generation != _loadGeneration) return;
      if (_trades.isEmpty) {
        setState(() {
          _error = 'Paper trades could not be refreshed. Pull down to try again.';
        });
      }
    } finally {
      if (mounted && generation == _loadGeneration) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> refresh() => _load();

  double? _number(dynamic value) {
    if (value is num) return value.toDouble();
    if (value == null) return null;
    final cleaned = value
        .toString()
        .replaceAll(r'$', '')
        .replaceAll(',', '')
        .replaceAll('%', '')
        .trim();
    return double.tryParse(cleaned);
  }

  String _price(dynamic value) {
    final number = _number(value);
    if (number == null) return value?.toString() ?? '—';
    return '\$${number.toStringAsFixed(2)}';
  }

  String _pnl(dynamic value) {
    final number = _number(value);
    if (number == null) return value?.toString() ?? '—';
    if (number > 0) return '+\$${number.toStringAsFixed(2)}';
    if (number < 0) return '-\$${number.abs().toStringAsFixed(2)}';
    return '\$0.00';
  }

  String _successLabel(Map<String, dynamic> trade, dynamic pnl) {
    final supplied = trade['success_label']?.toString().trim();
    if (supplied != null && supplied.isNotEmpty) return supplied.toUpperCase();
    final status = trade['status']?.toString().toUpperCase() ?? '';
    if (status != 'CLOSED') return 'IN PROGRESS';
    final number = _number(pnl);
    if (number == null) return 'UNKNOWN';
    return number > 0 ? 'YES' : 'NO';
  }

  Color _successColor(BuildContext context, String success) {
    switch (success) {
      case 'YES':
        return Colors.greenAccent;
      case 'NO':
        return Theme.of(context).colorScheme.error;
      default:
        return Theme.of(context).colorScheme.primary;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.signedIn) {
      return AccountRequiredState(
        feature: 'Paper Trades',
        onCreateAccount: widget.onCreateAccount,
      );
    }
    if (_loading) return const Center(child: CircularProgressIndicator());
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 130),
        children: [
          InstitutionalSectionLabel(
            label: 'Paper portfolio',
            trailing: Text(
              '${_trades.length} POSITIONS',
              style: const TextStyle(
                fontSize: 10,
                letterSpacing: .8,
                fontWeight: FontWeight.w800,
                color: Color(0xFF9CB0C7),
              ),
            ),
          ),
          AppCard(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.science_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Simulated paper trades',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                      SizedBox(height: 4),
                      Text(
                        'These positions are educational simulations. Oryntra AI does not connect to a brokerage or execute real orders.',
                        style: TextStyle(
                          fontSize: 12,
                          color: Color(0xFF9CB0C7),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (_error != null) AppCard(child: Text(_error!)),
          if (_trades.isEmpty)
            const EmptyState(
              icon: Icons.receipt_long_outlined,
              title: 'No paper trades',
              body:
                  'Open simulated trades on the website; they will appear here.',
            )
          else
            ..._trades.map((item) {
              final trade = Map<String, dynamic>.from(item as Map);
              final status = trade['status']?.toString().toUpperCase() ?? '—';
              final pnl = trade['current_pnl'] ?? trade['pnl'];
              final success = _successLabel(trade, pnl);
              final successColor = _successColor(context, success);
              return AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            trade['ticker']?.toString() ?? '—',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                        ),
                        Chip(label: Text(status)),
                      ],
                    ),
                    Text(
                      '${trade['direction'] ?? '—'} • ${trade['size'] ?? '—'} shares',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 12),
                    _TradeMetric('Entry price', _price(trade['entry_price'])),
                    _TradeMetric(
                      'Current price',
                      _price(trade['current_price']),
                    ),
                    if (status == 'CLOSED' && trade['close_price'] != null)
                      _TradeMetric('Exit price', _price(trade['close_price'])),
                    _TradeMetric('P&L', _pnl(pnl)),
                    _TradeMetric('Success', success, valueColor: successColor),
                    if (status != 'CLOSED') ...[
                      const SizedBox(height: 8),
                      const Text(
                        'Success remains in progress until the simulated position is closed.',
                        style: TextStyle(fontSize: 11, color: Colors.white60),
                      ),
                    ],
                  ],
                ),
              );
            }),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 16),
            child: AdaptiveBanner(),
          ),
        ],
      ),
    );
  }
}

class _TradeMetric extends StatelessWidget {
  const _TradeMetric(this.label, this.value, {this.valueColor});

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
            width: 112,
            child: Text(label, style: const TextStyle(color: Colors.white70)),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(color: valueColor, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }
}
