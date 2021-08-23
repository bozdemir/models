# Copyright 2021 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for targets generations of centernet."""

from absl.testing import parameterized

import tensorflow as tf

from official.vision.beta.projects.centernet.ops import target_assigner
from official.vision.beta.ops import preprocess_ops


class TargetAssignerTest(tf.test.TestCase, parameterized.TestCase):
  def check_labels_correct(self,
                           boxes,
                           classes,
                           output_size,
                           input_size,
                           use_odapi=False):
    max_num_instances = 128
    num_detections = len(boxes)
    boxes = tf.constant(boxes, dtype=tf.float32)
    classes = tf.constant(classes, dtype=tf.float32)
    
    boxes = preprocess_ops.clip_or_pad_to_fixed_size(
        boxes, max_num_instances, 0)
    classes = preprocess_ops.clip_or_pad_to_fixed_size(
        classes, max_num_instances, 0)
    
    labels = target_assigner.assign_centernet_targets(
        labels={
            'bbox': boxes,
            'num_detections': num_detections,
            'classes': classes
        },
        output_size=output_size,
        input_size=input_size,
        use_odapi_gaussian=use_odapi)
    
    ct_heatmaps = labels['ct_heatmaps']
    ct_offset = labels['ct_offset']
    size = labels['size']
    box_mask = labels['box_mask']
    box_indices = labels['box_indices']
    
    boxes = tf.cast(boxes, tf.float32)
    classes = tf.cast(classes, tf.float32)
    height_ratio = output_size[0] / input_size[0]
    width_ratio = output_size[1] / input_size[1]
    
    # Shape checks
    self.assertEqual(ct_heatmaps.shape, (output_size[0], output_size[1], 90))
    
    self.assertEqual(ct_offset.shape, (max_num_instances, 2))
    
    self.assertEqual(size.shape, (max_num_instances, 2))
    self.assertEqual(box_mask.shape, (max_num_instances,))
    self.assertEqual(box_indices.shape, (max_num_instances, 2))
    
    self.assertAllInRange(ct_heatmaps, 0, 1)
    
    for i in range(len(boxes)):
      # Check sizes
      self.assertAllEqual(size[i],
                          [(boxes[i][2] - boxes[i][0]) * height_ratio,
                           (boxes[i][3] - boxes[i][1]) * width_ratio,
                           ])
      
      # Check box indices
      y = tf.math.floor((boxes[i][0] + boxes[i][2]) / 2 * height_ratio)
      x = tf.math.floor((boxes[i][1] + boxes[i][3]) / 2 * width_ratio)
      self.assertAllEqual(box_indices[i], [y, x])
      
      # check offsets
      true_y = (boxes[i][0] + boxes[i][2]) / 2 * height_ratio
      true_x = (boxes[i][1] + boxes[i][3]) / 2 * width_ratio
      self.assertAllEqual(ct_offset[i], [true_y - y, true_x - x])
    
    for i in range(len(boxes), max_num_instances):
      # Make sure rest are zero
      self.assertAllEqual(size[i], [0, 0])
      self.assertAllEqual(box_indices[i], [0, 0])
      self.assertAllEqual(ct_offset[i], [0, 0])
    
    # Check mask indices
    self.assertAllEqual(tf.cast(box_mask[3:], tf.int32),
                        tf.repeat(0, repeats=max_num_instances - 3))
    self.assertAllEqual(tf.cast(box_mask[:3], tf.int32),
                        tf.repeat(1, repeats=3))
  
  @parameterized.parameters(True, False)
  def test_generate_targets_no_scale(self, use_odapi):
    boxes = [
        (10, 300, 15, 370),
        (100, 300, 150, 370),
        (15, 100, 200, 170),
    ]
    classes = (1, 2, 3)
    sizes = [512, 512]
    
    self.check_labels_correct(boxes=boxes,
                              classes=classes,
                              output_size=sizes,
                              input_size=sizes,
                              use_odapi=use_odapi)
  
  @parameterized.parameters(True, False)
  def test_generate_targets_stride_4(self, use_odapi):
    boxes = [
        (10, 300, 15, 370),
        (100, 300, 150, 370),
        (15, 100, 200, 170),
    ]
    classes = (1, 2, 3)
    output_size = [128, 128]
    input_size = [512, 512]
    
    self.check_labels_correct(boxes=boxes,
                              classes=classes,
                              output_size=output_size,
                              input_size=input_size,
                              use_odapi=use_odapi)
  
  @parameterized.parameters(True, False)
  def test_generate_targets_stride_8(self, use_odapi):
    boxes = [
        (10, 300, 15, 370),
        (100, 300, 150, 370),
        (15, 100, 200, 170),
    ]
    classes = (1, 2, 3)
    output_size = [128, 128]
    input_size = [1024, 1024]
    
    self.check_labels_correct(boxes=boxes,
                              classes=classes,
                              output_size=output_size,
                              input_size=input_size,
                              use_odapi=use_odapi)
  
  @parameterized.parameters(True, False)
  def test_batch_generate_targets(self, use_odapi):
    
    input_size = [512, 512]
    output_size = [128, 128]
    max_num_instances = 128
    
    boxes = tf.constant([
        (10, 300, 15, 370),  # center (y, x) = (12, 335)
        (100, 300, 150, 370),  # center (y, x) = (125, 335)
        (15, 100, 200, 170),  # center (y, x) = (107, 135)
    ], dtype=tf.float32)
    
    classes = tf.constant((1, 1, 1), dtype=tf.float32)
    
    boxes = preprocess_ops.clip_or_pad_to_fixed_size(
        boxes, max_num_instances, 0)
    classes = preprocess_ops.clip_or_pad_to_fixed_size(
        classes, max_num_instances, -1)
    
    boxes = tf.stack([boxes, boxes], axis=0)
    classes = tf.stack([classes, classes], axis=0)
    
    labels = tf.map_fn(
        fn=lambda x: target_assigner.assign_centernet_targets(
            labels=x,
            output_size=output_size,
            input_size=input_size,
            use_odapi_gaussian=use_odapi),
        elems={
            'bbox': boxes,
            'num_detections': tf.constant([3, 3]),
            'classes': classes
        },
        dtype={
            'ct_heatmaps': tf.float32,
            'ct_offset': tf.float32,
            'size': tf.float32,
            'box_mask': tf.int32,
            'box_indices': tf.int32
        }
    )
    
    ct_heatmaps = labels['ct_heatmaps']
    ct_offset = labels['ct_offset']
    size = labels['size']
    box_mask = labels['box_mask']
    box_indices = labels['box_indices']
    
    self.assertEqual(ct_heatmaps.shape, (2, output_size[0], output_size[1], 90))
    
    self.assertEqual(ct_offset.shape, (2, max_num_instances, 2))
    
    self.assertEqual(size.shape, (2, max_num_instances, 2))
    self.assertEqual(box_mask.shape, (2, max_num_instances))
    self.assertEqual(box_indices.shape, (2, max_num_instances, 2))


if __name__ == '__main__':
  tf.test.main()