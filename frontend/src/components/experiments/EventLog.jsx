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
  TablePagination,
  TextField,
  InputAdornment,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import {
  Refresh,
  Download,
  Search,
  Info,
  FilterList,
  Visibility,
  VisibilityOff
} from '@mui/icons-material';

const EventLog = ({ experimentId }) => {
  const [policy, setPolicy] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(100);
  const [searchTerm, setSearchTerm] = useState('');
  const [showContext, setShowContext] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [contextDialogOpen, setContextDialogOpen] = useState(false);

  const { data: eventData, isLoading, error, refetch } = useQuery({
    queryKey: ['experiment-events', experimentId, policy, page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        limit: rowsPerPage.toString(),
        offset: (page * rowsPerPage).toString()
      });
      if (policy) params.append('policy', policy);
      
      const response = await fetch(
        `/api/experiments/${experimentId}/events?${params}`
      );
      if (!response.ok) throw new Error('Failed to fetch event data');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!experimentId
  });

  // Filter events based on search term
  const filteredEvents = eventData?.events?.filter(event => 
    event.user_id.toString().includes(searchTerm) ||
    event.arm_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    event.policy?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    event.algorithm?.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];

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

  // Get reward color
  const getRewardColor = (reward) => {
    if (reward === null || reward === undefined) return 'text.secondary';
    if (reward > 0.5) return 'success.main';
    if (reward > 0.2) return 'warning.main';
    return 'error.main';
  };

  // Export to CSV
  const exportToCSV = async () => {
    try {
      const response = await fetch(`/api/experiments/${experimentId}/export?format=csv`);
      if (!response.ok) throw new Error('Failed to export data');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `experiment_${experimentId}_events.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Export failed:', error);
    }
  };

  // Handle page change
  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Show context dialog
  const showEventContext = (event) => {
    setSelectedEvent(event);
    setContextDialogOpen(true);
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Event Log" />
        <CardContent>
          <Skeleton variant="rectangular" height={400} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Event Log" />
        <CardContent>
          <Alert severity="error">
            Failed to load event data: {error.message}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader
          title={
            <Box display="flex" alignItems="center" gap={1}>
              <Typography variant="h6">Event Log</Typography>
              <Tooltip title="Real-time event log with pagination and filtering">
                <IconButton size="small">
                  <Info fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
          }
          action={
            <Box display="flex" alignItems="center" gap={2}>
              <TextField
                size="small"
                placeholder="Search events..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  ),
                }}
                sx={{ minWidth: 200 }}
              />
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Policy</InputLabel>
                <Select
                  value={policy}
                  label="Policy"
                  onChange={(e) => setPolicy(e.target.value)}
                >
                  <MenuItem value="">All Policies</MenuItem>
                  <MenuItem value="thompson">Thompson</MenuItem>
                  <MenuItem value="egreedy">ε-greedy</MenuItem>
                  <MenuItem value="ucb">UCB1</MenuItem>
                  <MenuItem value="control">Control</MenuItem>
                </Select>
              </FormControl>
              <Button
                variant="outlined"
                startIcon={<Download />}
                onClick={exportToCSV}
                size="small"
              >
                Export CSV
              </Button>
              <IconButton onClick={() => refetch()} size="small">
                <Refresh />
              </IconButton>
            </Box>
          }
        />
        <CardContent>
          {/* Event Table */}
          <TableContainer component={Paper} sx={{ maxHeight: 600 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Timestamp</TableCell>
                  <TableCell>User ID</TableCell>
                  <TableCell>Policy</TableCell>
                  <TableCell>Arm ID</TableCell>
                  <TableCell>Algorithm</TableCell>
                  <TableCell align="center">Position</TableCell>
                  <TableCell align="center">Score</TableCell>
                  <TableCell align="center">P-Score</TableCell>
                  <TableCell align="center">Latency</TableCell>
                  <TableCell align="center">Reward</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredEvents.map((event, index) => (
                  <TableRow key={event.id} hover>
                    <TableCell>
                      <Typography variant="body2">
                        {new Date(event.served_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {event.user_id}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={event.policy || 'N/A'}
                        size="small"
                        sx={{
                          backgroundColor: event.policy ? getPolicyColor(event.policy) : 'grey.300',
                          color: 'white',
                          fontWeight: 'bold'
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {event.arm_id || 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {event.algorithm}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {event.position}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {event.score ? event.score.toFixed(3) : 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {event.p_score ? event.p_score.toFixed(3) : 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {event.latency_ms ? `${event.latency_ms}ms` : 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography 
                        variant="body2"
                        color={getRewardColor(event.reward)}
                        fontWeight="bold"
                      >
                        {event.reward !== null ? event.reward.toFixed(3) : 'Pending'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <IconButton
                        size="small"
                        onClick={() => showEventContext(event)}
                        title="View context"
                      >
                        <Visibility />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Pagination */}
          <TablePagination
            rowsPerPageOptions={[50, 100, 200, 500]}
            component="div"
            count={eventData?.pagination?.total || 0}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handleChangePage}
            onRowsPerPageChange={handleChangeRowsPerPage}
            labelRowsPerPage="Rows per page:"
            labelDisplayedRows={({ from, to, count }) => 
              `${from}-${to} of ${count !== -1 ? count : `more than ${to}`}`
            }
          />

          {/* Summary Stats */}
          <Box mt={3} p={2} sx={{ backgroundColor: 'grey.50', borderRadius: 1 }}>
            <Typography variant="subtitle2" gutterBottom>
              Event Summary
            </Typography>
            <Box display="flex" gap={3} flexWrap="wrap">
              <Box display="flex" alignItems="center" gap={1}>
                <Typography variant="body2">Total Events:</Typography>
                <Typography variant="body2" fontWeight="bold">
                  {eventData?.pagination?.total?.toLocaleString() || 0}
                </Typography>
              </Box>
              <Box display="flex" alignItems="center" gap={1}>
                <Typography variant="body2">Filtered Events:</Typography>
                <Typography variant="body2" fontWeight="bold">
                  {filteredEvents.length.toLocaleString()}
                </Typography>
              </Box>
              <Box display="flex" alignItems="center" gap={1}>
                <Typography variant="body2">Has More:</Typography>
                <Typography variant="body2" fontWeight="bold">
                  {eventData?.pagination?.has_more ? 'Yes' : 'No'}
                </Typography>
              </Box>
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Context Dialog */}
      <Dialog
        open={contextDialogOpen}
        onClose={() => setContextDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Event Context - {selectedEvent?.id}
        </DialogTitle>
        <DialogContent>
          {selectedEvent && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Event Details
              </Typography>
              <Box component="pre" sx={{ 
                backgroundColor: 'grey.100', 
                p: 2, 
                borderRadius: 1,
                overflow: 'auto',
                fontSize: '0.875rem'
              }}>
                {JSON.stringify({
                  id: selectedEvent.id,
                  user_id: selectedEvent.user_id,
                  algorithm: selectedEvent.algorithm,
                  position: selectedEvent.position,
                  score: selectedEvent.score,
                  policy: selectedEvent.policy,
                  arm_id: selectedEvent.arm_id,
                  p_score: selectedEvent.p_score,
                  latency_ms: selectedEvent.latency_ms,
                  reward: selectedEvent.reward,
                  served_at: selectedEvent.served_at
                }, null, 2)}
              </Box>
              
              <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
                Context
              </Typography>
              <Box component="pre" sx={{ 
                backgroundColor: 'grey.100', 
                p: 2, 
                borderRadius: 1,
                overflow: 'auto',
                fontSize: '0.875rem'
              }}>
                {JSON.stringify(selectedEvent.context, null, 2)}
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setContextDialogOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default EventLog;
