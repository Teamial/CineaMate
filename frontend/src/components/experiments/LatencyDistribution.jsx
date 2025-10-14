import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Box,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Alert,
  Skeleton,
  Tooltip,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  LinearProgress
} from '@mui/material';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  BoxPlot
} from 'recharts';
import {
  Refresh,
  Speed,
  Info,
  Warning,
  CheckCircle
} from '@mui/icons-material';

const LatencyDistribution = ({ experimentId }) => {
  const [granularity, setGranularity] = useState('hour');
  const [selectedPolicies, setSelectedPolicies] = useState(['thompson', 'egreedy', 'ucb']);

  const { data: latencyData, isLoading, error, refetch } = useQuery({
    queryKey: ['experiment-latency', experimentId, granularity],
    queryFn: async () => {
      const response = await fetch(
        `/api/experiments/${experimentId}/timeseries?metric=latency_p95&granularity=${granularity}`
      );
      if (!response.ok) throw new Error('Failed to fetch latency data');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!experimentId
  });

  const { data: summaryData } = useQuery({
    queryKey: ['experiment-summary', experimentId],
    queryFn: async () => {
      const response = await fetch(`/api/experiments/${experimentId}/summary`);
      if (!response.ok) throw new Error('Failed to fetch experiment summary');
      return response.json();
    },
    enabled: !!experimentId
  });

  // Process data for chart
  const processChartData = (data) => {
    if (!data) return [];

    // Group data by timestamp and policy
    const groupedData = {};
    
    data.forEach(item => {
      const timestamp = item.timestamp;
      if (!groupedData[timestamp]) {
        groupedData[timestamp] = { timestamp };
      }
      groupedData[timestamp][item.policy] = item.value;
    });

    // Convert to array and sort by timestamp
    return Object.values(groupedData)
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  };

  const chartData = processChartData(latencyData);

  // Get policy colors
  const getPolicyColor = (policy) => {
    const colors = {
      thompson: '#1976d2',
      egreedy: '#388e3c',
      ucb: '#f57c00',
      control: '#757575'
    };
    return colors[policy] || '#9e9e9e';
  };

  // Calculate latency percentiles
  const calculateLatencyPercentiles = (data) => {
    if (!data) return {};

    const percentiles = {};
    const policies = ['thompson', 'egreedy', 'ucb', 'control'];

    policies.forEach(policy => {
      const policyLatencies = data
        .map(item => item[policy])
        .filter(val => val !== undefined && val !== null);
      
      if (policyLatencies.length > 0) {
        const sorted = policyLatencies.sort((a, b) => a - b);
        const len = sorted.length;
        
        percentiles[policy] = {
          p50: sorted[Math.floor(len * 0.5)],
          p90: sorted[Math.floor(len * 0.9)],
          p95: sorted[Math.floor(len * 0.95)],
          p99: sorted[Math.floor(len * 0.99)],
          min: sorted[0],
          max: sorted[len - 1],
          mean: policyLatencies.reduce((sum, val) => sum + val, 0) / len
        };
      }
    });

    return percentiles;
  };

  const latencyPercentiles = calculateLatencyPercentiles(chartData);

  // Check SLA compliance
  const checkSLACompliance = (percentiles) => {
    const slaThreshold = 120; // 120ms SLA
    const compliance = {};

    Object.entries(percentiles).forEach(([policy, stats]) => {
      compliance[policy] = {
        p95Compliant: stats.p95 < slaThreshold,
        p99Compliant: stats.p99 < slaThreshold * 1.5, // 180ms for p99
        overallCompliant: stats.p95 < slaThreshold && stats.p99 < slaThreshold * 1.5
      };
    });

    return compliance;
  };

  const slaCompliance = checkSLACompliance(latencyPercentiles);

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <Box
          sx={{
            backgroundColor: 'white',
            border: '1px solid #ccc',
            borderRadius: 1,
            p: 2,
            boxShadow: 2
          }}
        >
          <Typography variant="body2" color="text.secondary" mb={1}>
            {new Date(label).toLocaleString()}
          </Typography>
          {payload.map((entry, index) => (
            <Box key={index} display="flex" alignItems="center" gap={1} mb={0.5}>
              <Box
                width={12}
                height={12}
                sx={{ backgroundColor: entry.color, borderRadius: '50%' }}
              />
              <Typography variant="body2">
                {entry.dataKey}: {entry.value?.toFixed(1) || 0}ms
              </Typography>
            </Box>
          ))}
        </Box>
      );
    }
    return null;
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Latency Distribution" />
        <CardContent>
          <Skeleton variant="rectangular" height={400} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Latency Distribution" />
        <CardContent>
          <Alert severity="error">
            Failed to load latency data: {error.message}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title={
          <Box display="flex" alignItems="center" gap={1}>
            <Speed color="primary" />
            <Typography variant="h6">Latency Distribution</Typography>
            <Tooltip title="P95 latency over time and SLA compliance">
              <IconButton size="small">
                <Info fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        }
        action={
          <Box display="flex" alignItems="center" gap={2}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Granularity</InputLabel>
              <Select
                value={granularity}
                label="Granularity"
                onChange={(e) => setGranularity(e.target.value)}
              >
                <MenuItem value="hour">Hour</MenuItem>
                <MenuItem value="day">Day</MenuItem>
              </Select>
            </FormControl>
            <IconButton onClick={() => refetch()} size="small">
              <Refresh />
            </IconButton>
          </Box>
        }
      />
      <CardContent>
        {/* SLA Compliance Status */}
        <Box mb={3}>
          <Typography variant="subtitle2" gutterBottom>
            SLA Compliance Status (P95 &lt; 120ms)
          </Typography>
          <Box display="flex" gap={2} flexWrap="wrap">
            {Object.entries(slaCompliance).map(([policy, compliance]) => (
              <Chip
                key={policy}
                icon={compliance.overallCompliant ? <CheckCircle /> : <Warning />}
                label={`${policy}: ${compliance.p95Compliant ? 'PASS' : 'FAIL'}`}
                color={compliance.overallCompliant ? 'success' : 'error'}
                variant="outlined"
                sx={{ textTransform: 'capitalize' }}
              />
            ))}
          </Box>
        </Box>

        {/* Chart */}
        <Box height={400} mb={3}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(value) => new Date(value).toLocaleTimeString()}
                stroke="#666"
              />
              <YAxis
                label={{ value: 'P95 Latency (ms)', angle: -90, position: 'insideLeft' }}
                stroke="#666"
              />
              <RechartsTooltip content={<CustomTooltip />} />
              <Legend />
              
              {/* Policy Bars */}
              {selectedPolicies.map(policy => (
                <Bar
                  key={policy}
                  dataKey={policy}
                  fill={getPolicyColor(policy)}
                  name={policy.charAt(0).toUpperCase() + policy.slice(1)}
                />
              ))}
              
              {/* SLA Reference Line */}
              <ReferenceLine
                y={120}
                stroke="#ff9800"
                strokeDasharray="5 5"
                label={{ value: "SLA (120ms)", position: "topRight" }}
              />
            </BarChart>
          </ResponsiveContainer>
        </Box>

        {/* Latency Percentiles Table */}
        <Typography variant="subtitle2" gutterBottom>
          Latency Percentiles by Policy
        </Typography>
        <TableContainer component={Paper} sx={{ maxHeight: 300 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Policy</TableCell>
                <TableCell align="center">P50</TableCell>
                <TableCell align="center">P90</TableCell>
                <TableCell align="center">P95</TableCell>
                <TableCell align="center">P99</TableCell>
                <TableCell align="center">Mean</TableCell>
                <TableCell align="center">SLA Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(latencyPercentiles).map(([policy, stats]) => {
                const compliance = slaCompliance[policy];
                
                return (
                  <TableRow key={policy}>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Box
                          width={12}
                          height={12}
                          sx={{ backgroundColor: getPolicyColor(policy), borderRadius: '50%' }}
                        />
                        <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                          {policy}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {stats.p50.toFixed(1)}ms
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {stats.p90.toFixed(1)}ms
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography 
                        variant="body2"
                        color={compliance.p95Compliant ? 'success.main' : 'error.main'}
                        fontWeight="bold"
                      >
                        {stats.p95.toFixed(1)}ms
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography 
                        variant="body2"
                        color={compliance.p99Compliant ? 'success.main' : 'error.main'}
                      >
                        {stats.p99.toFixed(1)}ms
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {stats.mean.toFixed(1)}ms
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        icon={compliance.overallCompliant ? <CheckCircle /> : <Warning />}
                        label={compliance.overallCompliant ? 'PASS' : 'FAIL'}
                        color={compliance.overallCompliant ? 'success' : 'error'}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>

        {/* SLA Progress Bars */}
        <Box mt={3} p={2} sx={{ backgroundColor: 'grey.50', borderRadius: 1 }}>
          <Typography variant="subtitle2" gutterBottom>
            SLA Compliance Progress
          </Typography>
          {Object.entries(latencyPercentiles).map(([policy, stats]) => {
            const compliance = slaCompliance[policy];
            const p95Progress = Math.min((stats.p95 / 120) * 100, 100);
            
            return (
              <Box key={policy} mb={2}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                    {policy} P95
                  </Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {stats.p95.toFixed(1)}ms / 120ms
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={p95Progress}
                  sx={{
                    height: 8,
                    borderRadius: 4,
                    backgroundColor: 'rgba(0,0,0,0.1)',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: compliance.p95Compliant ? '#4caf50' : '#f44336'
                    }
                  }}
                />
              </Box>
            );
          })}
        </Box>
      </CardContent>
    </Card>
  );
};

export default LatencyDistribution;
