import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Box,
  Typography,
  Chip,
  Alert,
  Skeleton,
  Tooltip,
  IconButton,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  LinearProgress
} from '@mui/material';
import {
  Refresh,
  Warning,
  CheckCircle,
  Error,
  Info,
  Speed,
  TrendingDown,
  TrendingUp,
  Security,
  Rollback
} from '@mui/icons-material';

const GuardrailStatus = ({ experimentId }) => {
  const [rollbackDialogOpen, setRollbackDialogOpen] = useState(false);

  const { data: guardrailData, isLoading, error, refetch } = useQuery({
    queryKey: ['experiment-guardrails', experimentId],
    queryFn: async () => {
      const response = await fetch(`/api/experiments/${experimentId}/guardrails`);
      if (!response.ok) throw new Error('Failed to fetch guardrail data');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!experimentId
  });

  // Get guardrail icon
  const getGuardrailIcon = (status) => {
    switch (status) {
      case 'pass':
        return <CheckCircle color="success" />;
      case 'fail':
        return <Error color="error" />;
      case 'warning':
        return <Warning color="warning" />;
      default:
        return <Info color="info" />;
    }
  };

  // Get guardrail color
  const getGuardrailColor = (status) => {
    switch (status) {
      case 'pass':
        return 'success';
      case 'fail':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  };

  // Get guardrail severity
  const getGuardrailSeverity = (status) => {
    switch (status) {
      case 'fail':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  };

  // Handle rollback
  const handleRollback = async () => {
    try {
      // This would call the rollback API endpoint
      console.log('Rolling back experiment:', experimentId);
      setRollbackDialogOpen(false);
      // Show success message
    } catch (error) {
      console.error('Rollback failed:', error);
      // Show error message
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Guardrail Status" />
        <CardContent>
          <Skeleton variant="rectangular" height={400} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Guardrail Status" />
        <CardContent>
          <Alert severity="error">
            Failed to load guardrail data: {error.message}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const { overall_status, guardrails, recent_metrics } = guardrailData || {};

  return (
    <>
      <Card>
        <CardHeader
          title={
            <Box display="flex" alignItems="center" gap={1}>
              <Security color="primary" />
              <Typography variant="h6">Guardrail Status</Typography>
              <Tooltip title="Real-time guardrail monitoring and auto-rollback controls">
                <IconButton size="small">
                  <Info fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
          }
          action={
            <Box display="flex" alignItems="center" gap={2}>
              <Chip
                icon={getGuardrailIcon(overall_status)}
                label={overall_status?.toUpperCase() || 'UNKNOWN'}
                color={getGuardrailColor(overall_status)}
                variant="filled"
                sx={{ fontWeight: 'bold' }}
              />
              <IconButton onClick={() => refetch()} size="small">
                <Refresh />
              </IconButton>
            </Box>
          }
        />
        <CardContent>
          {/* Overall Status Alert */}
          {overall_status === 'fail' && (
            <Alert severity="error" sx={{ mb: 3 }}>
              <Typography variant="body2">
                <strong>CRITICAL:</strong> Multiple guardrails have failed. 
                Consider immediate rollback to prevent user experience degradation.
              </Typography>
            </Alert>
          )}

          {overall_status === 'warning' && (
            <Alert severity="warning" sx={{ mb: 3 }}>
              <Typography variant="body2">
                <strong>WARNING:</strong> Some guardrails are showing concerning trends. 
                Monitor closely and consider intervention.
              </Typography>
            </Alert>
          )}

          {overall_status === 'pass' && (
            <Alert severity="success" sx={{ mb: 3 }}>
              <Typography variant="body2">
                <strong>HEALTHY:</strong> All guardrails are passing. 
                Experiment is running within acceptable parameters.
              </Typography>
            </Alert>
          )}

          {/* Guardrail Details */}
          <Typography variant="subtitle2" gutterBottom>
            Guardrail Details
          </Typography>
          <List>
            {Object.entries(guardrails || {}).map(([name, guardrail]) => (
              <ListItem key={name} sx={{ px: 0 }}>
                <ListItemIcon>
                  {getGuardrailIcon(guardrail.status)}
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Box display="flex" alignItems="center" gap={1}>
                      <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                        {name.replace('_', ' ')}
                      </Typography>
                      <Chip
                        label={guardrail.status}
                        size="small"
                        color={getGuardrailColor(guardrail.status)}
                        variant="outlined"
                      />
                    </Box>
                  }
                  secondary={
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        {guardrail.message}
                      </Typography>
                      <Box display="flex" alignItems="center" gap={2} mt={1}>
                        <Typography variant="caption">
                          Current: {guardrail.value}
                        </Typography>
                        <Typography variant="caption">
                          Threshold: {guardrail.threshold}
                        </Typography>
                        {guardrail.value > guardrail.threshold && (
                          <TrendingUp fontSize="small" color="error" />
                        )}
                        {guardrail.value < guardrail.threshold && (
                          <TrendingDown fontSize="small" color="success" />
                        )}
                      </Box>
                    </Box>
                  }
                />
              </ListItem>
            ))}
          </List>

          <Divider sx={{ my: 2 }} />

          {/* Recent Metrics */}
          <Typography variant="subtitle2" gutterBottom>
            Recent Metrics (Last 30 minutes)
          </Typography>
          <Box display="flex" gap={3} flexWrap="wrap" mb={3}>
            <Box display="flex" flexDirection="column" alignItems="center">
              <Typography variant="h6" color="primary">
                {recent_metrics?.total_events?.toLocaleString() || 0}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Total Events
              </Typography>
            </Box>
            <Box display="flex" flexDirection="column" alignItems="center">
              <Typography variant="h6" color="primary">
                {recent_metrics?.avg_latency?.toFixed(1) || 0}ms
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Avg Latency
              </Typography>
            </Box>
            <Box display="flex" flexDirection="column" alignItems="center">
              <Typography variant="h6" color="primary">
                {recent_metrics?.p95_latency?.toFixed(1) || 0}ms
              </Typography>
              <Typography variant="caption" color="text.secondary">
                P95 Latency
              </Typography>
            </Box>
            <Box display="flex" flexDirection="column" alignItems="center">
              <Typography variant="h6" color="primary">
                {recent_metrics?.avg_reward?.toFixed(3) || 0}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Avg Reward
              </Typography>
            </Box>
          </Box>

          {/* Rollback Controls */}
          <Box p={2} sx={{ backgroundColor: 'grey.50', borderRadius: 1 }}>
            <Typography variant="subtitle2" gutterBottom>
              Emergency Controls
            </Typography>
            <Box display="flex" gap={2} alignItems="center">
              <Button
                variant="contained"
                color="error"
                startIcon={<Rollback />}
                onClick={() => setRollbackDialogOpen(true)}
                disabled={overall_status === 'pass'}
              >
                Rollback Experiment
              </Button>
              <Typography variant="caption" color="text.secondary">
                This will immediately stop the experiment and revert to the control policy.
              </Typography>
            </Box>
          </Box>

          {/* Status History */}
          <Box mt={3}>
            <Typography variant="subtitle2" gutterBottom>
              Status History
            </Typography>
            <Box display="flex" gap={1} flexWrap="wrap">
              {['pass', 'pass', 'pass', 'warning', 'pass'].map((status, index) => (
                <Chip
                  key={index}
                  label={status}
                  size="small"
                  color={getGuardrailColor(status)}
                  variant="outlined"
                />
              ))}
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Last 5 checks (every 5 minutes)
            </Typography>
          </Box>
        </CardContent>
      </Card>

      {/* Rollback Confirmation Dialog */}
      <Dialog
        open={rollbackDialogOpen}
        onClose={() => setRollbackDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <Warning color="error" />
            Confirm Experiment Rollback
          </Box>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" gutterBottom>
            Are you sure you want to rollback this experiment? This action will:
          </Typography>
          <List dense>
            <ListItem>
              <ListItemIcon>
                <Error color="error" />
              </ListItemIcon>
              <ListItemText primary="Immediately stop the experiment" />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <Error color="error" />
              </ListItemIcon>
              <ListItemText primary="Revert all users to the control policy" />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <Error color="error" />
              </ListItemIcon>
              <ListItemText primary="Preserve all experiment data for analysis" />
            </ListItem>
          </List>
          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body2">
              <strong>Warning:</strong> This action cannot be undone. 
              The experiment will be permanently stopped.
            </Typography>
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRollbackDialogOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleRollback}
            color="error"
            variant="contained"
            startIcon={<Rollback />}
          >
            Confirm Rollback
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default GuardrailStatus;
