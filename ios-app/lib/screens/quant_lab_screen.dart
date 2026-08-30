import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../widgets/common.dart';
import '../widgets/glass.dart';

class QuantLabScreen extends StatefulWidget {
  const QuantLabScreen({super.key, required this.api});

  final ApiService api;

  @override
  State<QuantLabScreen> createState() => QuantLabScreenState();
}

class QuantLabScreenState extends State<QuantLabScreen> {
  final _tickers = TextEditingController(text: 'SPY, QQQ, IWM, TLT');
  String _period = '2y';
  String _model = 'v1_corporate_quant_system';
  String _rebalance = 'weekly';
  double _targetVolatility = 12;
  double _costBps = 12;
  double _maxNameWeight = 35;
  bool _longShort = true;
  bool _regimeWeights = true;
  bool _liquidityCosts = true;
  bool _running = false;
  String _progress = '';
  String? _error;
  Map<String, dynamic>? _report;
  final Set<String> _strategies = {
    'time_series_trend',
    'cross_sectional_momentum',
    'mean_reversion',
    'defensive_low_volatility',
    'corporate_quality',
  };

  @override
  void dispose() {
    _tickers.dispose();
    super.dispose();
  }

  Map<String, double> _weights() => {
    'time_series_trend': _strategies.contains('time_series_trend') ? 25 : 0,
    'cross_sectional_momentum': _strategies.contains('cross_sectional_momentum')
        ? 25
        : 0,
    'mean_reversion': _strategies.contains('mean_reversion') ? 10 : 0,
    'defensive_low_volatility': _strategies.contains('defensive_low_volatility')
        ? 15
        : 0,
    'corporate_quality': _strategies.contains('corporate_quality') ? 25 : 0,
  };

  Future<void> _run() async {
    final symbols = _tickers.text.split(',');
    if (_strategies.isEmpty) {
      setState(() => _error = 'Select at least one research sleeve.');
      return;
    }
    setState(() {
      _running = true;
      _error = null;
      _report = null;
      _progress =
          'Feel free to take a break and switch apps, this scan may take a minute.';
    });
    try {
      final report = await widget.api.runQuantResearch(
        tickers: symbols,
        period: _period,
        model: _model,
        strategies: _strategies.toList(),
        strategyWeights: _weights(),
        lookback: 126,
        targetVolatility: _targetVolatility,
        maxGrossExposure: 1,
        maxNameWeight: _maxNameWeight / 100,
        rebalanceFrequency: _rebalance,
        costBps: _costBps,
        borrowBps: 50,
        longShort: _longShort,
        regimeConditionedWeights: _regimeWeights,
        liquidityAwareCosts: _liquidityCosts,
        onProgress: (message) async {
          if (mounted) setState(() => _progress = message);
        },
      );
      if (mounted) setState(() => _report = report);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) {
        setState(() {
          _running = false;
          _progress = '';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = OryntraColors.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 130),
      children: [
        const InstitutionalSectionLabel(label: 'Systematic research desk'),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 3, 20, 10),
          child: Text(
            'Quant Lab',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Text(
            'Generate a report with sleeve returns, a portfolio equity path, drawdown, simulated costs, current hypothetical weights, regime history, and a chronological holdout. It does not execute orders.',
            style: TextStyle(color: colors.muted, height: 1.45),
          ),
        ),
        const SizedBox(height: 10),
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Research specification',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _tickers,
                textCapitalization: TextCapitalization.characters,
                autocorrect: false,
                decoration: const InputDecoration(
                  labelText: 'Universe',
                  hintText: 'SPY, QQQ, IWM, TLT',
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _period,
                decoration: const InputDecoration(labelText: 'Sample window'),
                items: const [
                  DropdownMenuItem(value: '1y', child: Text('1 year')),
                  DropdownMenuItem(value: '2y', child: Text('2 years')),
                  DropdownMenuItem(value: '5y', child: Text('5 years')),
                  DropdownMenuItem(value: 'all', child: Text('All available')),
                ],
                onChanged: _running
                    ? null
                    : (value) => setState(() => _period = value!),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _model,
                decoration: const InputDecoration(labelText: 'Research model'),
                items: const [
                  DropdownMenuItem(
                    value: 'v1_corporate_quant_system',
                    child: Text('V1.0 corporate quant system'),
                  ),
                  DropdownMenuItem(
                    value: 'v8_regime_diversified',
                    child: Text('V1.0 diversified price baseline'),
                  ),
                  DropdownMenuItem(
                    value: 'v8_trend_first',
                    child: Text('V1.0 trend-first price baseline'),
                  ),
                  DropdownMenuItem(
                    value: 'v8_relative_strength',
                    child: Text('V1.0 relative-strength baseline'),
                  ),
                ],
                onChanged: _running
                    ? null
                    : (value) => setState(() => _model = value!),
              ),
            ],
          ),
        ),
        const InstitutionalSectionLabel(label: 'Strategy sleeves'),
        AppCard(
          child: Column(
            children: [
              _strategyToggle(
                'time_series_trend',
                'Trend',
                'Persistent direction across each symbol.',
              ),
              _strategyToggle(
                'cross_sectional_momentum',
                'Relative strength',
                'Rank leaders and laggards in the universe.',
              ),
              _strategyToggle(
                'mean_reversion',
                'Mean reversion',
                'Contrarian comparator after large moves.',
              ),
              _strategyToggle(
                'defensive_low_volatility',
                'Defensive low volatility',
                'Favor lower realized-volatility baskets.',
              ),
              _strategyToggle(
                'corporate_quality',
                'Corporate quality',
                'Use time-stamped public fundamental evidence when available.',
              ),
            ],
          ),
        ),
        const InstitutionalSectionLabel(label: 'Portfolio controls'),
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _slider(
                'Target annual volatility',
                _targetVolatility,
                6,
                25,
                '%',
                (value) => setState(() => _targetVolatility = value),
              ),
              _slider(
                'Max name weight',
                _maxNameWeight,
                10,
                50,
                '%',
                (value) => setState(() => _maxNameWeight = value),
              ),
              _slider(
                'Trading cost',
                _costBps,
                0,
                75,
                ' bps',
                (value) => setState(() => _costBps = value),
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                value: _rebalance,
                decoration: const InputDecoration(labelText: 'Rebalance'),
                items: const [
                  DropdownMenuItem(value: 'daily', child: Text('Daily')),
                  DropdownMenuItem(value: 'weekly', child: Text('Weekly')),
                  DropdownMenuItem(value: 'monthly', child: Text('Monthly')),
                ],
                onChanged: _running
                    ? null
                    : (value) => setState(() => _rebalance = value!),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('Long / short research'),
                subtitle: const Text('Research simulation only.'),
                value: _longShort,
                onChanged: _running
                    ? null
                    : (value) => setState(() => _longShort = value),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('Regime-conditioned weights'),
                subtitle: const Text(
                  'Condition sleeves on reported market state.',
                ),
                value: _regimeWeights,
                onChanged: _running
                    ? null
                    : (value) => setState(() => _regimeWeights = value),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('Liquidity-aware costs'),
                subtitle: const Text(
                  'Apply impact and participation diagnostics.',
                ),
                value: _liquidityCosts,
                onChanged: _running
                    ? null
                    : (value) => setState(() => _liquidityCosts = value),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
          child: Text(
            'Mobile runs request daily bars directly from your saved provider key. The default four-symbol universe fits Polygon / Massive Basic’s five-calls-per-minute allowance.',
            style: TextStyle(fontSize: 11, color: colors.muted),
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (_running)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: colors.blueBright.withValues(alpha: .09),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: colors.blueBright.withValues(alpha: .28),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const LinearProgressIndicator(),
                  const SizedBox(height: 11),
                  const Text(
                    'Feel free to take a break and switch apps, this scan may take a minute.',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    _progress,
                    style: TextStyle(fontSize: 11, color: colors.muted),
                  ),
                ],
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.all(20),
          child: FilledButton.icon(
            onPressed: _running ? null : _run,
            icon: _running
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.science_outlined),
            label: Text(
              _running
                  ? 'Building research report…'
                  : 'Generate research report',
            ),
          ),
        ),
        if (_report != null) _QuantReport(report: _report!),
      ],
    );
  }

  Widget _strategyToggle(String id, String title, String subtitle) =>
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        value: _strategies.contains(id),
        onChanged: _running
            ? null
            : (value) => setState(
                () => value == true
                    ? _strategies.add(id)
                    : _strategies.remove(id),
              ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Text(subtitle),
        controlAffinity: ListTileControlAffinity.leading,
      );

  Widget _slider(
    String label,
    double value,
    double min,
    double max,
    String suffix,
    ValueChanged<double> onChanged,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
          Text('${value.round()}$suffix'),
        ],
      ),
      Slider(
        value: value,
        min: min,
        max: max,
        divisions: (max - min).round(),
        onChanged: _running ? null : onChanged,
      ),
    ],
  );
}

class _QuantReport extends StatelessWidget {
  const _QuantReport({required this.report});
  final Map<String, dynamic> report;

  String _number(dynamic value, {String suffix = '', int digits = 1}) {
    final number = value is num
        ? value.toDouble()
        : double.tryParse(value?.toString() ?? '');
    return number == null
        ? '—'
        : '${number >= 0 ? '+' : ''}${number.toStringAsFixed(digits)}$suffix';
  }

  @override
  Widget build(BuildContext context) {
    final risk = report['portfolio_risk'] is Map
        ? Map<String, dynamic>.from(report['portfolio_risk'])
        : <String, dynamic>{};
    final validation = report['validation'] is Map
        ? Map<String, dynamic>.from(report['validation'])
        : <String, dynamic>{};
    final holdout = validation['holdout'] is Map
        ? Map<String, dynamic>.from(validation['holdout'])
        : <String, dynamic>{};
    final regimes = report['regime_breakdown'] is List
        ? List<dynamic>.from(report['regime_breakdown'])
        : const [];
    final health = report['strategy_health'] is List
        ? List<dynamic>.from(report['strategy_health'])
        : const [];
    return Column(
      children: [
        const InstitutionalSectionLabel(label: 'Research report'),
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Dataset fingerprint',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              SelectableText(
                (report['dataset_fingerprint']?.toString() ?? '—').substring(
                  0,
                  (report['dataset_fingerprint']?.toString().length ?? 0).clamp(
                        0,
                        28,
                      )
                      as int,
                ),
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _metric(
                    'Holdout return',
                    _number(holdout['total_return_pct'], suffix: '%'),
                  ),
                  _metric(
                    'Holdout drawdown',
                    _number(holdout['max_drawdown_pct'], suffix: '%'),
                  ),
                  _metric(
                    'Gross exposure',
                    _number(
                      risk['latest_gross_exposure'],
                      suffix: '×',
                      digits: 2,
                    ),
                  ),
                  _metric(
                    'Effective positions',
                    _number(risk['effective_number_of_positions'], digits: 2),
                  ),
                ],
              ),
            ],
          ),
        ),
        if (regimes.isNotEmpty) ...[
          const InstitutionalSectionLabel(label: 'Regime report'),
          AppCard(
            child: Column(
              children: regimes
                  .whereType<Map>()
                  .map(
                    (item) => ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        item['regime']?.toString() ?? 'Historical state',
                      ),
                      subtitle: Text(
                        '${item['sessions'] ?? '—'} sessions · vol ${_number(item['annualized_volatility_pct'], suffix: '%')}',
                      ),
                      trailing: Text(
                        _number(item['total_return_pct'], suffix: '%'),
                        style: const TextStyle(fontWeight: FontWeight.w900),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
        if (health.isNotEmpty) ...[
          const InstitutionalSectionLabel(label: 'Strategy health'),
          AppCard(
            child: Column(
              children: health
                  .whereType<Map>()
                  .map(
                    (item) => ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(item['strategy']?.toString() ?? 'Sleeve'),
                      subtitle: Text(
                        'Recent ${_number(item['recent_mean_daily_bps'], suffix: ' bps', digits: 2)} · decay ${_number(item['alpha_decay_daily_bps'], suffix: ' bps', digits: 2)}',
                      ),
                      trailing: Text(
                        item['status']?.toString() ?? '—',
                        style: const TextStyle(fontWeight: FontWeight.w900),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      ],
    );
  }

  Widget _metric(String label, String value) => Container(
    width: 145,
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: Colors.black.withValues(alpha: .06),
      borderRadius: BorderRadius.circular(13),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
        ),
      ],
    ),
  );
}
