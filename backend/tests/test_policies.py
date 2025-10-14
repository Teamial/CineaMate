"""
Unit Tests for Multi-Armed Bandit Policies

Tests the core policy implementations (Thompson Sampling, ε-greedy, UCB1),
reward calculator, and experiment manager with comprehensive coverage.

Test Coverage:
- Policy selection logic and state updates
- Propensity score calculations
- Reward computation and time windows
- User assignment and traffic control
- Edge cases and error handling

Usage:
    pytest backend/tests/test_policies.py -v
    pytest backend/tests/test_reward_calculator.py -v
    pytest backend/tests/test_experiment_manager.py -v
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

# Import the modules to test
from backend.ml.policies.thompson_sampling import ThompsonSamplingPolicy
from backend.ml.policies.epsilon_greedy import EpsilonGreedyPolicy
from backend.ml.policies.ucb1 import UCB1Policy
from backend.ml.policies.base import PolicyStateStore
from backend.ml.reward_calculator import RewardCalculator
from backend.ml.experiment_manager import ExperimentManager
from backend.models import RecommendationEvent, PolicyState, Experiment, PolicyAssignment

class TestThompsonSamplingPolicy:
    """Test Thompson Sampling policy implementation"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def thompson_policy(self, mock_db):
        """Thompson Sampling policy instance"""
        return ThompsonSamplingPolicy(mock_db)
    
    def test_policy_name(self, thompson_policy):
        """Test policy name is correct"""
        assert thompson_policy.name == "thompson"
    
    def test_cold_start_selection(self, thompson_policy, mock_db):
        """Test cold start arm selection"""
        # Mock empty state store
        with patch.object(thompson_policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.alpha = 1.0
            mock_state.beta = 1.0
            mock_get_state.return_value = mock_state
            
            # Test selection with cold arms
            arms = ['arm1', 'arm2', 'arm3']
            context = {'user_type': 'new'}
            
            result = thompson_policy.select(context, arms)
            
            # Should select one of the arms
            assert result.arm_id in arms
            assert result.confidence >= 0.0
            assert result.p_score == 1.0 / len(arms)  # Uniform probability for cold start
    
    def test_exploitation_selection(self, thompson_policy, mock_db):
        """Test exploitation of high-reward arms"""
        # Mock state with different alpha/beta values
        with patch.object(thompson_policy.store, 'get_state') as mock_get_state:
            def mock_get_state_side_effect(arm_id, context_key='default'):
                mock_state = Mock()
                if arm_id == 'good_arm':
                    mock_state.alpha = 10.0  # High success rate
                    mock_state.beta = 2.0
                else:
                    mock_state.alpha = 2.0   # Lower success rate
                    mock_state.beta = 10.0
                return mock_state
            
            mock_get_state.side_effect = mock_get_state_side_effect
            
            # Test multiple selections
            arms = ['good_arm', 'bad_arm']
            context = {'user_type': 'regular'}
            
            selections = []
            for _ in range(100):
                result = thompson_policy.select(context, arms)
                selections.append(result.arm_id)
            
            # Good arm should be selected more often
            good_arm_selections = sum(1 for arm in selections if arm == 'good_arm')
            assert good_arm_selections > 50  # Should be biased toward good arm
    
    def test_state_update(self, thompson_policy, mock_db):
        """Test policy state updates"""
        with patch.object(thompson_policy.store, 'update_thompson_state') as mock_update:
            arm_id = 'test_arm'
            reward = 1.0
            context = {'user_type': 'regular'}
            
            thompson_policy.update(arm_id, reward, context)
            
            mock_update.assert_called_once_with(arm_id, reward, 'default')
    
    def test_alpha_beta_updates(self, thompson_policy, mock_db):
        """Test alpha/beta parameter updates"""
        with patch.object(thompson_policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.alpha = 1.0
            mock_state.beta = 1.0
            mock_get_state.return_value = mock_state
            
            # Test positive reward update
            thompson_policy.update('test_arm', 1.0, {})
            assert mock_state.alpha == 2.0  # Should increment
            assert mock_state.beta == 1.0   # Should not change
            
            # Test negative reward update
            thompson_policy.update('test_arm', 0.0, {})
            assert mock_state.alpha == 2.0  # Should not change
            assert mock_state.beta == 2.0   # Should increment

class TestEpsilonGreedyPolicy:
    """Test ε-greedy policy implementation"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def epsilon_policy(self, mock_db):
        """ε-greedy policy instance"""
        return EpsilonGreedyPolicy(mock_db, epsilon=0.1)
    
    def test_policy_name(self, epsilon_policy):
        """Test policy name is correct"""
        assert epsilon_policy.name == "egreedy"
    
    def test_epsilon_parameter(self, epsilon_policy):
        """Test epsilon parameter"""
        assert epsilon_policy.epsilon == 0.1
    
    def test_cold_start_selection(self, epsilon_policy, mock_db):
        """Test cold start arm selection"""
        with patch.object(epsilon_policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.count = 0  # Cold start
            mock_get_state.return_value = mock_state
            
            arms = ['arm1', 'arm2']
            context = {'user_type': 'new'}
            
            result = epsilon_policy.select(context, arms)
            
            # Should select one of the cold arms
            assert result.arm_id in arms
            assert result.p_score == 1.0 / len(arms)
    
    def test_exploitation_selection(self, epsilon_policy, mock_db):
        """Test exploitation of best arm"""
        with patch.object(epsilon_policy.store, 'get_state') as mock_get_state:
            def mock_get_state_side_effect(arm_id, context_key='default'):
                mock_state = Mock()
                if arm_id == 'best_arm':
                    mock_state.count = 100
                    mock_state.mean_reward = 0.8
                else:
                    mock_state.count = 100
                    mock_state.mean_reward = 0.3
                return mock_state
            
            mock_get_state.side_effect = mock_get_state_side_effect
            
            # Mock random to force exploitation
            with patch('random.random', return_value=0.05):  # Below epsilon
                arms = ['best_arm', 'worst_arm']
                context = {'user_type': 'regular'}
                
                result = epsilon_policy.select(context, arms)
                
                # Should select best arm
                assert result.arm_id == 'best_arm'
                assert result.p_score > 0.9  # High probability for exploitation
    
    def test_exploration_selection(self, epsilon_policy, mock_db):
        """Test exploration with random selection"""
        with patch.object(epsilon_policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.count = 100
            mock_state.mean_reward = 0.5
            mock_get_state.return_value = mock_state
            
            # Mock random to force exploration
            with patch('random.random', return_value=0.15):  # Above epsilon
                arms = ['arm1', 'arm2']
                context = {'user_type': 'regular'}
                
                result = epsilon_policy.select(context, arms)
                
                # Should select randomly
                assert result.arm_id in arms
                assert result.p_score == epsilon_policy.epsilon / len(arms)
    
    def test_tie_breaking(self, epsilon_policy, mock_db):
        """Test tie-breaking when multiple arms have same reward"""
        with patch.object(epsilon_policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.count = 100
            mock_state.mean_reward = 0.5  # Same for all arms
            mock_get_state.return_value = mock_state
            
            arms = ['arm1', 'arm2', 'arm3']
            context = {'user_type': 'regular'}
            
            # Test multiple selections to ensure tie-breaking works
            selections = []
            for _ in range(10):
                result = epsilon_policy.select(context, arms)
                selections.append(result.arm_id)
            
            # Should select different arms due to tie-breaking
            unique_selections = set(selections)
            assert len(unique_selections) > 1

class TestUCB1Policy:
    """Test UCB1 policy implementation"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def ucb_policy(self, mock_db):
        """UCB1 policy instance"""
        return UCB1Policy(mock_db)
    
    def test_policy_name(self, ucb_policy):
        """Test policy name is correct"""
        assert ucb_policy.name == "ucb"
    
    def test_cold_start_selection(self, ucb_policy, mock_db):
        """Test cold start arm selection"""
        with patch.object(ucb_policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.count = 0  # Cold start
            mock_get_state.return_value = mock_state
            
            arms = ['arm1', 'arm2']
            context = {'user_type': 'new'}
            
            result = ucb_policy.select(context, arms)
            
            # Should select one of the cold arms
            assert result.arm_id in arms
            assert result.p_score is None  # UCB1 doesn't provide p_score
    
    def test_ucb_formula(self, ucb_policy, mock_db):
        """Test UCB formula calculation"""
        with patch.object(ucb_policy.store, 'get_state') as mock_get_state:
            def mock_get_state_side_effect(arm_id, context_key='default'):
                mock_state = Mock()
                if arm_id == 'explored_arm':
                    mock_state.count = 100
                    mock_state.mean_reward = 0.5
                else:
                    mock_state.count = 10
                    mock_state.mean_reward = 0.6
                return mock_state
            
            mock_get_state.side_effect = mock_get_state_side_effect
            
            arms = ['explored_arm', 'less_explored_arm']
            context = {'user_type': 'regular'}
            
            result = ucb_policy.select(context, arms)
            
            # Should select less explored arm due to higher confidence bonus
            assert result.arm_id == 'less_explored_arm'
            assert result.confidence > 0.6  # Should include confidence bonus
    
    def test_confidence_bounds(self, ucb_policy, mock_db):
        """Test that confidence bounds decrease with more pulls"""
        with patch.object(ucb_policy.store, 'get_state') as mock_get_state:
            def mock_get_state_side_effect(arm_id, context_key='default'):
                mock_state = Mock()
                mock_state.count = 1000  # Many pulls
                mock_state.mean_reward = 0.5
                return mock_state
            
            mock_get_state.side_effect = mock_get_state_side_effect
            
            arms = ['arm1']
            context = {'user_type': 'regular'}
            
            result = ucb_policy.select(context, arms)
            
            # Confidence should be close to mean reward with many pulls
            assert abs(result.confidence - 0.5) < 0.1

class TestRewardCalculator:
    """Test reward calculation logic"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def reward_calculator(self, mock_db):
        """Reward calculator instance"""
        return RewardCalculator(mock_db, reward_window_hours=24)
    
    def test_click_reward(self, reward_calculator):
        """Test reward for click interaction"""
        event = Mock()
        event.served_at = datetime.utcnow()
        event.clicked = True
        event.clicked_at = datetime.utcnow() + timedelta(minutes=5)
        event.rated = False
        event.thumbs_up = False
        event.added_to_watchlist = False
        event.added_to_favorites = False
        
        reward = reward_calculator.compute_reward(event)
        assert reward == 1.0
    
    def test_rating_reward(self, reward_calculator):
        """Test reward for high rating"""
        event = Mock()
        event.served_at = datetime.utcnow()
        event.clicked = False
        event.rated = True
        event.rated_at = datetime.utcnow() + timedelta(minutes=10)
        event.rating_value = 4.5
        event.thumbs_up = False
        event.added_to_watchlist = False
        event.added_to_favorites = False
        
        reward = reward_calculator.compute_reward(event)
        assert reward == 1.0
    
    def test_low_rating_reward(self, reward_calculator):
        """Test reward for low rating"""
        event = Mock()
        event.served_at = datetime.utcnow()
        event.clicked = False
        event.rated = True
        event.rated_at = datetime.utcnow() + timedelta(minutes=10)
        event.rating_value = 1.5
        event.thumbs_up = False
        event.added_to_watchlist = False
        event.added_to_favorites = False
        
        reward = reward_calculator.compute_reward(event)
        assert reward == 0.0
    
    def test_thumbs_up_reward(self, reward_calculator):
        """Test reward for thumbs up"""
        event = Mock()
        event.served_at = datetime.utcnow()
        event.clicked = False
        event.rated = False
        event.thumbs_up = True
        event.thumbs_up_at = datetime.utcnow() + timedelta(minutes=15)
        event.added_to_watchlist = False
        event.added_to_favorites = False
        
        reward = reward_calculator.compute_reward(event)
        assert reward == 1.0
    
    def test_watchlist_reward(self, reward_calculator):
        """Test reward for watchlist addition"""
        event = Mock()
        event.served_at = datetime.utcnow()
        event.clicked = False
        event.rated = False
        event.thumbs_up = False
        event.added_to_watchlist = True
        event.added_to_favorites = False
        event.created_at = datetime.utcnow() + timedelta(minutes=20)
        
        reward = reward_calculator.compute_reward(event)
        assert reward == 1.0
    
    def test_no_interaction_reward(self, reward_calculator):
        """Test reward for no interaction"""
        event = Mock()
        event.served_at = datetime.utcnow() - timedelta(hours=25)  # Past window
        event.clicked = False
        event.rated = False
        event.thumbs_up = False
        event.added_to_watchlist = False
        event.added_to_favorites = False
        
        reward = reward_calculator.compute_reward(event)
        assert reward == 0.0
    
    def test_pending_reward(self, reward_calculator):
        """Test reward still pending"""
        event = Mock()
        event.served_at = datetime.utcnow() - timedelta(hours=1)  # Within window
        event.clicked = False
        event.rated = False
        event.thumbs_up = False
        event.added_to_watchlist = False
        event.added_to_favorites = False
        
        reward = reward_calculator.compute_reward(event)
        assert reward is None
    
    def test_window_expired(self, reward_calculator):
        """Test reward window expiration"""
        event = Mock()
        event.served_at = datetime.utcnow() - timedelta(hours=25)  # Past window
        event.clicked = False
        event.rated = False
        event.thumbs_up = False
        event.added_to_watchlist = False
        event.added_to_favorites = False
        
        reward = reward_calculator.compute_reward(event)
        assert reward == 0.0

class TestExperimentManager:
    """Test experiment manager functionality"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def experiment_manager(self, mock_db):
        """Experiment manager instance"""
        return ExperimentManager(mock_db)
    
    def test_user_bucket_assignment(self, experiment_manager):
        """Test deterministic user bucket assignment"""
        user_id = 12345
        bucket1 = experiment_manager._get_user_bucket(user_id)
        bucket2 = experiment_manager._get_user_bucket(user_id)
        
        # Should be deterministic
        assert bucket1 == bucket2
        assert 0 <= bucket1 <= 99
    
    def test_different_users_different_buckets(self, experiment_manager):
        """Test different users get different buckets"""
        buckets = set()
        for user_id in range(1000, 1010):
            bucket = experiment_manager._get_user_bucket(user_id)
            buckets.add(bucket)
        
        # Should have some diversity in buckets
        assert len(buckets) > 1
    
    def test_experiment_not_found(self, experiment_manager, mock_db):
        """Test handling of non-existent experiment"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(ValueError, match="Experiment.*not found"):
            experiment_manager.get_active_experiment("non-existent-id")
    
    def test_user_assignment_new_user(self, experiment_manager, mock_db):
        """Test assignment of new user to policy"""
        # Mock experiment
        mock_experiment = Mock()
        mock_experiment.traffic_pct = 0.8
        mock_experiment.default_policy = 'thompson'
        
        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment
        
        # Mock user bucket to be in traffic
        with patch.object(experiment_manager, '_get_user_bucket', return_value=50):
            with patch('random.choice', return_value='thompson'):
                policy, bucket = experiment_manager.assign_user_to_policy(
                    "exp-id", 12345, ['thompson', 'egreedy']
                )
                
                assert policy == 'thompson'
                assert bucket == 50
    
    def test_user_assignment_out_of_traffic(self, experiment_manager, mock_db):
        """Test assignment of user outside traffic percentage"""
        # Mock experiment
        mock_experiment = Mock()
        mock_experiment.traffic_pct = 0.5  # 50% traffic
        mock_experiment.default_policy = 'control'
        
        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment
        
        # Mock user bucket to be outside traffic
        with patch.object(experiment_manager, '_get_user_bucket', return_value=75):
            policy, bucket = experiment_manager.assign_user_to_policy(
                "exp-id", 12345, ['thompson', 'egreedy']
            )
            
            assert policy == 'control'
            assert bucket == 75
    
    def test_existing_assignment(self, experiment_manager, mock_db):
        """Test retrieval of existing user assignment"""
        # Mock existing assignment
        mock_assignment = Mock()
        mock_assignment.policy = 'thompson'
        mock_assignment.bucket = 25
        
        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.return_value = mock_assignment
        
        policy, bucket = experiment_manager.assign_user_to_policy(
            "exp-id", 12345, ['thompson', 'egreedy']
        )
        
        assert policy == 'thompson'
        assert bucket == 25

class TestPolicyStateStore:
    """Test policy state store functionality"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def state_store(self, mock_db):
        """Policy state store instance"""
        return PolicyStateStore(mock_db, "test_policy")
    
    def test_get_state_new(self, state_store, mock_db):
        """Test getting state for new arm"""
        # Mock no existing state
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Mock new state creation
        mock_state = Mock()
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None
        
        state = state_store.get_state("new_arm", "default")
        
        # Should create new state
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    
    def test_get_state_existing(self, state_store, mock_db):
        """Test getting existing state"""
        # Mock existing state
        mock_state = Mock()
        mock_state.policy = "test_policy"
        mock_state.arm_id = "existing_arm"
        mock_state.context_key = "default"
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_state
        
        state = state_store.get_state("existing_arm", "default")
        
        # Should return existing state
        assert state == mock_state
        mock_db.add.assert_not_called()
    
    def test_update_state(self, state_store, mock_db):
        """Test state update"""
        # Mock existing state
        mock_state = Mock()
        mock_state.count = 10
        mock_state.sum_reward = 5.0
        mock_state.mean_reward = 0.5
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_state
        
        state_store.update_state("test_arm", 1.0, "default")
        
        # Should update state
        assert mock_state.count == 11
        assert mock_state.sum_reward == 6.0
        assert mock_state.mean_reward == 6.0 / 11
        mock_db.commit.assert_called_once()
    
    def test_update_thompson_state(self, state_store, mock_db):
        """Test Thompson Sampling state update"""
        # Mock existing state
        mock_state = Mock()
        mock_state.count = 10
        mock_state.sum_reward = 5.0
        mock_state.mean_reward = 0.5
        mock_state.alpha = 5.0
        mock_state.beta = 5.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_state
        
        state_store.update_thompson_state("test_arm", 1.0, "default")
        
        # Should update state
        assert mock_state.count == 11
        assert mock_state.sum_reward == 6.0
        assert mock_state.mean_reward == 6.0 / 11
        assert mock_state.alpha == 6.0  # Should increment for positive reward
        assert mock_state.beta == 5.0  # Should not change

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
