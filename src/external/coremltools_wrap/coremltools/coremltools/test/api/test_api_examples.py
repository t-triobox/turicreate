from os import getcwd, chdir
from shutil import rmtree
from os.path import exists
from tempfile import mkdtemp
import pytest
import numpy as np
import coremltools as ct
import os

from coremltools._deps import (
    _HAS_TF_1,
    _HAS_TF_2,
    _HAS_TORCH,
    MSG_TF1_NOT_FOUND,
    MSG_TF2_NOT_FOUND,
    MSG_TORCH_NOT_FOUND,
)


###############################################################################
# Note: all tests are also used as examples such as in readme.md as a reference
# Whenever any of the following test fails, we should update API documentations
# Each test case is expected to be runnable and self-complete, then sync to the
# documentation pages as API example code snippet.
###############################################################################


@pytest.mark.skipif(not _HAS_TF_1, reason=MSG_TF1_NOT_FOUND)
@pytest.mark.skipif(ct.utils._macos_version() < (10, 15), reason='Model produces specification 4.')
class TestTensorFlow1ConverterExamples:

    @staticmethod
    def test_convert_from_frozen_graph(tmpdir):
        import tensorflow as tf

        with tf.Graph().as_default() as graph:
            x = tf.placeholder(tf.float32, shape=(1, 2, 3), name="input")
            y = tf.nn.relu(x, name="output")

        mlmodel = ct.convert(graph)

        test_input = np.random.rand(1, 2, 3) - 0.5
        with tf.compat.v1.Session(graph=graph) as sess:
            expected_val = sess.run(y, feed_dict={x: test_input})
        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["output"], expected_val)

    @staticmethod
    def test_convert_from_frozen_graph_file(tmpdir):
        # create the model to convert
        import tensorflow as tf

        # write a toy frozen graph
        # Note that we usually needs to run freeze_graph() on tf.Graph()
        # skipping here as this toy model does not contain any variables
        with tf.Graph().as_default() as graph:
            x = tf.placeholder(tf.float32, shape=(1, 2, 3), name="input")
            y = tf.nn.relu(x, name="output")

        save_path = str(tmpdir)
        tf.io.write_graph(graph, save_path, "frozen_graph.pb", as_text=False)

        # Create a test sample
        # -0.5 to have some negative values
        test_input = np.random.rand(1, 2, 3) - 0.5
        with tf.compat.v1.Session(graph=graph) as sess:
            expected_val = sess.run(y, feed_dict={x: test_input})

        # The input `.pb` file is a frozen graph format that usually
        # generated by TensorFlow's utility function `freeze_graph()`
        pb_path = os.path.join(save_path, "frozen_graph.pb")

        # 3 ways to specify inputs:
        # (1) Fully specify inputs
        mlmodel = ct.convert(
            pb_path,
            # We specify inputs with name matching the placeholder name.
            inputs=[ct.TensorType(name="input", shape=(1, 2, 3))],
            outputs=["output"],
        )

        # (2) Specify input TensorType without name (when there's only one
        # input)
        mlmodel = ct.convert(
            pb_path,
            # TensorType name is optional when there's only one input.
            inputs=[ct.TensorType(shape=(1, 2, 3))],
            outputs=["output"],
        )

        # (3) Not specify inputs at all. `inputs` is optional for TF. When
        # inputs is not specified, convert() infers inputs from Placeholder
        # nodes.
        mlmodel = ct.convert(pb_path, outputs=["output"])

        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["output"], expected_val)
        mlmodel_path = os.path.join(save_path, "model.mlmodel")
        # Save the converted model
        mlmodel.save(mlmodel_path)

        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["output"], expected_val)

    @staticmethod
    def test_convert_from_saved_model_dir(tmpdir):
        # Sample input
        test_input = np.random.rand(1, 3, 5) - 0.5

        # create the model to convert
        import tensorflow as tf

        with tf.compat.v1.Session() as sess:
            x = tf.placeholder(shape=(1, 3, 5), dtype=tf.float32)
            y = tf.nn.relu(x)

            expected_val = sess.run(y, feed_dict={x: test_input})

        # Save model as SavedModel
        inputs = {"x": x}
        outputs = {"y": y}
        save_path = str(tmpdir)
        tf.compat.v1.saved_model.simple_save(sess, save_path, inputs, outputs)

        # SavedModel directory generated by TensorFlow 1.x
        # when converting from SavedModel dir, inputs / outputs are optional
        mlmodel = ct.convert(save_path)

        # Need input output names to call mlmodel
        # x.name == 'Placeholder:0'. Strip out ':0'
        input_name = x.name.split(":")[0]
        results = mlmodel.predict({input_name: test_input})
        # y.name == 'Relu:0'. output_name == 'Relu'
        output_name = y.name.split(":")[0]
        np.testing.assert_allclose(results[output_name], expected_val)


    @staticmethod
    def test_freeze_and_convert_matmul_graph():
        # testing : https://coremltools.readme.io/docs/tensorflow-1#export-as-frozen-graph-and-convert

        import tensorflow as tf

        graph = tf.Graph()
        with graph.as_default():
            x = tf.placeholder(tf.float32, shape=[None, 20], name="input")
            W = tf.Variable(tf.truncated_normal([20, 10], stddev=0.1))
            b = tf.Variable(tf.ones([10]))
            y = tf.matmul(x, W) + b
            output_names = [y.op.name]

        import tempfile
        import os
        from tensorflow.python.tools.freeze_graph import freeze_graph

        model_dir = tempfile.mkdtemp()
        graph_def_file = os.path.join(model_dir, 'tf_graph.pb')
        checkpoint_file = os.path.join(model_dir, 'tf_model.ckpt')
        frozen_graph_file = os.path.join(model_dir, 'tf_frozen.pb')

        with tf.Session(graph=graph) as sess:
            # initialize variables
            sess.run(tf.global_variables_initializer())
            # save graph definition somewhere
            tf.train.write_graph(sess.graph, model_dir, graph_def_file, as_text=False)
            # save the weights
            saver = tf.train.Saver()
            saver.save(sess, checkpoint_file)

            # take the graph definition and weights
            # and freeze into a single .pb frozen graph file
            freeze_graph(input_graph=graph_def_file,
                         input_saver="",
                         input_binary=True,
                         input_checkpoint=checkpoint_file,
                         output_node_names=",".join(output_names),
                         restore_op_name="save/restore_all",
                         filename_tensor_name="save/Const:0",
                         output_graph=frozen_graph_file,
                         clear_devices=True,
                         initializer_nodes="")
        print("Tensorflow frozen graph saved at {}".format(frozen_graph_file))

        mlmodel = ct.convert(frozen_graph_file)
        # optionally, you can save model to disk
        # mlmodel.save(frozen_graph_file.replace("pb", "mlmodel"))
        import shutil
        try:
            shutil.rmtree(model_dir)
        except:
            pass


@pytest.mark.skipif(not _HAS_TF_2, reason=MSG_TF2_NOT_FOUND)
class TestTensorFlow2ConverterExamples:
    def setup_class(self):
        self._cwd = getcwd()
        self._temp_dir = mkdtemp()
        # step into temp directory as working directory
        # to make the user-facing examples cleaner
        chdir(self._temp_dir)

        # create toy models for conversion examples
        import tensorflow as tf

        # write a toy tf.keras HDF5 model
        tf_keras_model = tf.keras.Sequential(
            [
                tf.keras.layers.Flatten(input_shape=(28, 28)),
                tf.keras.layers.Dense(128, activation=tf.nn.relu),
                tf.keras.layers.Dense(10, activation=tf.nn.softmax),
            ]
        )
        tf_keras_model.save("./tf_keras_model.h5")

        # write a toy SavedModel directory
        tf_keras_model.save("./saved_model", save_format="tf")

    def teardown_class(self):
        chdir(self._cwd)
        if exists(self._temp_dir):
            rmtree(self._temp_dir)

    @staticmethod
    def test_convert_tf_keras_h5_file(tmpdir):
        import tensorflow as tf

        x = tf.keras.Input(shape=(32,), name="input")
        y = tf.keras.layers.Dense(16, activation="softmax")(x)
        keras_model = tf.keras.Model(x, y)
        save_dir = str(tmpdir)
        h5_path = os.path.join(save_dir, "tf_keras_model.h5")
        keras_model.save(h5_path)

        mlmodel = ct.convert(h5_path)

        test_input = np.random.rand(2, 32)
        expected_val = keras_model(test_input)
        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["Identity"], expected_val, rtol=1e-4)

    @staticmethod
    def test_convert_tf_keras_model():
        import tensorflow as tf

        x = tf.keras.Input(shape=(32,), name="input")
        y = tf.keras.layers.Dense(16, activation="softmax")(x)
        keras_model = tf.keras.Model(x, y)

        mlmodel = ct.convert(keras_model)

        test_input = np.random.rand(2, 32)
        expected_val = keras_model(test_input)
        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["Identity"], expected_val, rtol=1e-4)

    @staticmethod
    def test_convert_tf_keras_applications_model():
        import tensorflow as tf

        tf_keras_model = tf.keras.applications.MobileNet(
            weights="imagenet", input_shape=(224, 224, 3)
        )

        # inputs / outputs are optional, we can get from tf.keras model
        # this can be extremely helpful when we want to extract sub-graphs
        input_name = tf_keras_model.inputs[0].name.split(":")[0]
        # note that the `convert()` requires tf.Graph's outputs instead of
        # tf.keras.Model's outputs, to access that, we can do the following
        output_name = tf_keras_model.outputs[0].name.split(":")[0]
        tf_graph_output_name = output_name.split("/")[-1]

        mlmodel = ct.convert(
            tf_keras_model,
            inputs=[ct.TensorType(shape=(1, 224, 224, 3))],
            outputs=[tf_graph_output_name],
        )
        mlmodel.save("./mobilenet.mlmodel")

    @staticmethod
    def test_convert_from_saved_model_dir():
        # SavedModel directory generated by TensorFlow 2.x
        mlmodel = ct.convert("./saved_model")
        mlmodel.save("./model.mlmodel")


    @staticmethod
    def test_keras_custom_layer_model():
        # testing : https://coremltools.readme.io/docs/tensorflow-2#conversion-from-user-defined-models

        import tensorflow as tf
        from tensorflow import keras
        from tensorflow.keras import layers

        class CustomDense(layers.Layer):
            def __init__(self, units=32):
                super(CustomDense, self).__init__()
                self.units = units

            def build(self, input_shape):
                self.w = self.add_weight(
                    shape=(input_shape[-1], self.units),
                    initializer="random_normal",
                    trainable=True,
                )
                self.b = self.add_weight(
                    shape=(self.units,), initializer="random_normal", trainable=True
                )

            def call(self, inputs):
                return tf.matmul(inputs, self.w) + self.b

        inputs = keras.Input((4,))
        outputs = CustomDense(10)(inputs)
        model = keras.Model(inputs, outputs)
        ct.convert(model)

    @staticmethod
    def test_concrete_function_conversion():
        # testing : https://coremltools.readme.io/docs/tensorflow-2#conversion-from-user-defined-models

        import tensorflow as tf

        @tf.function(input_signature=[tf.TensorSpec(shape=(6,), dtype=tf.float32)])
        def gelu_tanh_activation(x):
            a = (np.sqrt(2 / np.pi) * (x + 0.044715 * tf.pow(x, 3)))
            y = 0.5 * (1.0 + tf.tanh(a))
            return x * y

        conc_func = gelu_tanh_activation.get_concrete_function()
        ct.convert([conc_func])


    @staticmethod
    def test_quickstart_example():
        # testing: https://coremltools.readme.io/docs/introductory-quickstart#quickstart-example
        import tensorflow as tf  # TF 2.2.0

        # Download MobileNetv2 (using tf.keras)
        keras_model = tf.keras.applications.MobileNetV2(
            weights="imagenet",
            input_shape=(224, 224, 3,),
            classes=1000,
        )

        # Download class labels (from a separate file)
        import urllib
        label_url = 'https://storage.googleapis.com/download.tensorflow.org/data/ImageNetLabels.txt'
        class_labels = urllib.request.urlopen(label_url).read().splitlines()
        class_labels = class_labels[1:]  # remove the first class which is background
        assert len(class_labels) == 1000

        # make sure entries of class_labels are strings
        for i, label in enumerate(class_labels):
            if isinstance(label, bytes):
                class_labels[i] = label.decode("utf8")

        image_input = ct.ImageType(shape=(1, 224, 224, 3,),
                                   bias=[-1, -1, -1], scale=1 / 127)

        # set class labels
        classifier_config = ct.ClassifierConfig(class_labels)

        # Convert the model using the Unified Conversion API
        model = ct.convert(
            keras_model, inputs=[image_input], classifier_config=classifier_config,
        )

        # Set feature descriptions (these show up as comments in XCode)
        model.input_description["input_1"] = "Input image to be classified"
        model.output_description["classLabel"] = "Most likely image category"
        model.author = "Original Paper: Mark Sandler, Andrew Howard, "\
                        "Menglong Zhu, Andrey Zhmoginov, Liang-Chieh Chen"
        model.license = "Please see https://github.com/tensorflow/tensorflow "\
                        "for license information, and "\
                        "https://github.com/tensorflow/models/tree/master/research/slim/nets/mobilenet"\
                        "for the original source of the model."
        model.short_description = "Detects the dominant objects present in an"\
                                 "image from a set of 1001 categories such as trees, animals,"\
                                 "food, vehicles, person etc. The top-1 accuracy"\
                                " from the original publication is 74.7%."
        model.version = "2.0"

        # get an image
        from PIL import Image
        import requests
        from io import BytesIO

        img_url = 'https://files.readme.io/02e3586-daisy.jpg'
        response = requests.get(img_url)
        img = Image.open(BytesIO(response.content))

        # Use PIL to load and resize the image to expected size
        example_image = img.resize((224, 224))

        # Make a prediction using Core ML
        out_dict = model.predict({"input_1": example_image})

        # Print out top-1 prediction
        assert out_dict["classLabel"] == "daisy"

@pytest.mark.skipif(not _HAS_TORCH, reason=MSG_TORCH_NOT_FOUND)
class TestPyTorchConverterExamples:
    @staticmethod
    def test_convert_torch_vision_mobilenet_v2(tmpdir):
        import torch
        import torchvision

        """
        In this example, we'll instantiate a PyTorch classification model and convert
        it to Core ML.
        """

        """
        Here we instantiate our model. In a real use case this would be your trained
        model.
        """
        model = torchvision.models.mobilenet_v2()

        """
        The next thing we need to do is generate TorchScript for the model. The easiest
        way to do this is by tracing it.
        """

        """
        It's important that a model be in evaluation mode (not training mode) when it's
        traced. This makes sure things like dropout are disabled.
        """
        model.eval()

        """
        Tracing takes an example input and traces its flow through the model. Here we
        are creating an example image input.

        The rank and shape of the tensor will depend on your model use case. If your
        model expects a fixed size input, use that size here. If it can accept a
        variety of input sizes, it's generally best to keep the example input small to
        shorten how long it takes to run a forward pass of your model. In all cases,
        the rank of the tensor must be fixed.
        """
        example_input = torch.rand(1, 3, 256, 256)

        """
        Now we actually trace the model. This will produce the TorchScript that the
        CoreML converter needs.
        """
        traced_model = torch.jit.trace(model, example_input)

        """
        Now with a TorchScript representation of the model, we can call the CoreML
        converter. The converter also needs a description of the input to the model,
        where we can give it a convenient name.
        """
        mlmodel = ct.convert(
            traced_model,
            inputs=[ct.TensorType(name="input", shape=example_input.shape)],
        )

        """
        Now with a conversion complete, we can save the MLModel and run inference.
        """
        save_path = os.path.join(str(tmpdir), "mobilenet_v2.mlmodel")
        mlmodel.save(save_path)

        """
        Running predict() is only supported on macOS.
        """
        if ct.utils._is_macos():
            results = mlmodel.predict({"input": example_input.numpy()})
            expected = model(example_input)
            np.testing.assert_allclose(
                list(results.values())[0], expected.detach().numpy(), rtol=1e-2
            )

    @staticmethod
    def test_int64_inputs():
        import torch

        num_tokens = 3
        embedding_size = 5

        class TestModule(torch.nn.Module):
            def __init__(self):
                super(TestModule, self).__init__()
                self.embedding = torch.nn.Embedding(num_tokens, embedding_size)

            def forward(self, x):
                return self.embedding(x)

        model = TestModule()
        model.eval()

        example_input = torch.randint(high=num_tokens, size=(2,), dtype=torch.int64)
        traced_model = torch.jit.trace(model, example_input)
        mlmodel = ct.convert(
            traced_model,
            inputs=[
                ct.TensorType(
                    name="input",
                    shape=example_input.shape,
                    dtype=example_input.numpy().dtype,
                )
            ],
        )

        # running predict() is supported on macOS
        if ct.utils._is_macos():
            result = mlmodel.predict(
                {"input": example_input.detach().numpy().astype(np.float32)}
            )

            # Verify outputs
            expected = model(example_input)
            np.testing.assert_allclose(result["5"], expected.detach().numpy())

        # Duplicated inputs are invalid
        with pytest.raises(ValueError, match=r"Duplicated inputs"):
            mlmodel = ct.convert(
                traced_model,
                inputs=[
                    ct.TensorType(
                        name="input",
                        shape=example_input.shape,
                        dtype=example_input.numpy().dtype,
                    ),
                    ct.TensorType(
                        name="input",
                        shape=example_input.shape,
                        dtype=example_input.numpy().dtype,
                    ),
                ],
            )

        # Outputs must not be specified for PyTorch
        with pytest.raises(ValueError, match=r"outputs must not be specified"):
            mlmodel = ct.convert(
                traced_model,
                inputs=[
                    ct.TensorType(
                        name="input",
                        shape=example_input.shape,
                        dtype=example_input.numpy().dtype,
                    ),
                ],
                outputs=["output"],
            )


class TestMILExamples:
    @staticmethod
    def test_tutorial():
        from coremltools.converters.mil import Builder as mb

        @mb.program(
            input_specs=[mb.TensorSpec(shape=(1, 100, 100, 3)),]
        )
        def prog(x):
            x = mb.relu(x=x, name="relu")
            x = mb.transpose(x=x, perm=[0, 3, 1, 2], name="transpose")
            x = mb.reduce_mean(x=x, axes=[2, 3], keep_dims=False, name="reduce")
            x = mb.log(x=x, name="log")
            y = mb.add(x=1, y=2)
            return x

        print("prog:\n", prog)

        # Convert and verify
        from coremltools.converters.mil.converter import _convert
        from coremltools import models

        proto = _convert(prog, convert_from="mil")

        model = models.MLModel(proto)

        # running predict() is only supported on macOS
        if ct.utils._is_macos():
            prediction = model.predict(
                {"x": np.random.rand(1, 100, 100, 3).astype(np.float32),}
            )
            assert len(prediction) == 1
