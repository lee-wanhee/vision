import numpy as np
import os

import brainscore_vision.metric_helpers
from brainio.assemblies import NeuroidAssembly
from brainio.stimuli import StimulusSet
from brainscore_vision.benchmark_helpers.neural_common import average_repetition, timebins_from_assembly
from brainscore_vision.benchmarks import BenchmarkBase, ceil_score
from brainscore_vision.metrics.internal_consistency import InternalConsistency
from brainscore_vision.metrics.regression_correlation import CrossRegressedCorrelation, pls_regression, pearsonr_correlation
from brainscore_vision.model_helpers.brain_transformation import ModelCommitment, LayerSelection, RegionLayerMap
from brainscore_vision.model_interface import BrainModel


def check_brain_models(module):
    module = __import__(module)
    for model in module.get_model_list():
        model = module.get_model(model)
        assert model is not None
        assert isinstance(model, BrainModel)
        check_brain_model_processing(model)
    print('Test successful, you are ready to submit!')


def check_brain_model_processing(model):
    benchmark = _MockBenchmark()
    score = benchmark(model, do_behavior=True)
    assert score is not None


def check_base_models(module):
    module = __import__(module)
    for model in module.get_model_list():
        layers = module.get_layers(model)
        assert layers is not None
        assert isinstance(layers, list)
        assert len(layers) > 0
        assert module.get_model(model) is not None
        check_processing(model, module)
        print('Test successful, you are ready to submit!')


def check_processing(model_identifier, module):
    os.environ['RESULTCACHING_DISABLE'] = '1'
    model_instance = module.get_model(model_identifier)
    layers = module.get_layers(model_identifier)
    benchmark = _MockBenchmark()
    layer_selection = LayerSelection(model_identifier=model_identifier,
                                     activations_model=model_instance, layers=layers,
                                     visual_degrees=8)
    region_layer_map = RegionLayerMap(layer_selection=layer_selection,
                                      region_benchmarks={'IT': benchmark})

    brain_model = ModelCommitment(identifier=model_identifier, activations_model=model_instance,
                                  layers=layers, region_layer_map=region_layer_map)
    score = benchmark(brain_model, do_behavior=True)
    assert score is not None


class _MockBenchmark(BenchmarkBase):
    def __init__(self):
        assembly_repetition = get_assembly()
        assert len(np.unique(assembly_repetition['region'])) == 1
        assert hasattr(assembly_repetition, 'repetition')
        self.region = 'IT'
        self.assembly = average_repetition(assembly_repetition)
        self._assembly = self.assembly
        self.timebins = timebins_from_assembly(self.assembly)

        self._similarity_metric = CrossRegressedCorrelation(
            regression=pls_regression(), correlation=pearsonr_correlation(),
            crossvalidation_kwargs=dict(stratification_coord=brainscore_vision.metric_helpers.Defaults.stratification_coord
            if hasattr(self.assembly, brainscore_vision.metric_helpers.Defaults.stratification_coord) else None))
        identifier = f'{assembly_repetition.name}-layer_selection'
        ceiler = InternalConsistency()
        super(_MockBenchmark, self).__init__(identifier=identifier,
                                             ceiling_func=lambda: ceiler(assembly_repetition),
                                             version='1.0')

    def __call__(self, candidate: BrainModel, do_behavior=False):
        # Check neural recordings
        candidate.start_recording(self.region, time_bins=self.timebins)
        source_assembly = candidate.look_at(self.assembly.stimulus_set)
        # Check behavioral tasks
        if do_behavior:
            candidate.start_task(BrainModel.Task.probabilities, self.assembly.stimulus_set)
            candidate.look_at(self.assembly.stimulus_set)
        raw_score = self._similarity_metric(source_assembly, self.assembly)
        return ceil_score(raw_score, self.ceiling)


def get_assembly():
    image_names = []
    for i in range(1, 21):
        image_names.append(f'images/{i}.png')
    assembly = NeuroidAssembly((np.arange(40 * 5) + np.random.standard_normal(40 * 5)).reshape((5, 40, 1)),
                               coords={'stimulus_id': (
                                   'presentation',
                                   image_names * 2),
                                   'object_name': ('presentation', ['a'] * 40),
                                   'repetition': ('presentation', ([1] * 20 + [2] * 20)),
                                   'neuroid_id': ('neuroid', np.arange(5)),
                                   'region': ('neuroid', ['IT'] * 5),
                                   'time_bin_start': ('time_bin', [70]),
                                   'time_bin_end': ('time_bin', [170])
                               },
                               dims=['neuroid', 'presentation', 'time_bin'])
    labels = ['a'] * 10 + ['b'] * 10
    stimulus_set = StimulusSet([{'stimulus_id': image_names[i], 'object_name': 'a', 'image_label': labels[i]}
                                for i in range(20)])
    stimulus_set.stimulus_paths = {image_name: os.path.join(os.path.dirname(__file__), image_name)
                                   for image_name in image_names}
    stimulus_set.identifier = 'test'
    assembly.attrs['stimulus_set'] = stimulus_set
    assembly.attrs['stimulus_set_name'] = stimulus_set.identifier
    assembly = assembly.squeeze("time_bin")
    return assembly.transpose('presentation', 'neuroid')
